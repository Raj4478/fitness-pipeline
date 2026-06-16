"""
Label all existing YouTube videos as AI-generated content.
Required by YouTube policy for AI voices/visuals.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def main():
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install",
                       "google-auth-oauthlib", "google-api-python-client", "-q"])
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN"),
        client_id=os.environ.get("YOUTUBE_CLIENT_ID"),
        client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
    )
    youtube = build("youtube", "v3", credentials=creds)

    # ── Fetch all videos ───────────────────────────────────────────────
    logger.info("Fetching all channel videos...")
    all_video_ids = []
    next_page = None

    while True:
        params = {
            "part": "snippet",
            "forMine": True,
            "type": "video",
            "maxResults": 50,
        }
        if next_page:
            params["pageToken"] = next_page

        resp = youtube.search().list(**params).execute()
        items = resp.get("items", [])
        ids = [item["id"]["videoId"] for item in items]
        all_video_ids.extend(ids)
        logger.info("Fetched %d videos so far...", len(all_video_ids))

        next_page = resp.get("nextPageToken")
        if not next_page:
            break

    logger.info("Total videos found: %d", len(all_video_ids))

    # ── Label each video ───────────────────────────────────────────────
    success = 0
    failed = 0

    for i, video_id in enumerate(all_video_ids):
        try:
            # Get current video details first
            video_resp = youtube.videos().list(
                part="snippet,status",
                id=video_id,
            ).execute()

            if not video_resp.get("items"):
                logger.warning("Video %s not found — skipping", video_id)
                continue

            video = video_resp["items"][0]
            snippet = video["snippet"]
            status = video["status"]

            # Update with AI label
            youtube.videos().update(
                part="snippet,status",
                body={
                    "id": video_id,
                    "snippet": {
                        "title": snippet["title"],
                        "description": snippet.get("description", ""),
                        "categoryId": snippet.get("categoryId", "17"),
                        "tags": snippet.get("tags", []),
                        "defaultLanguage": snippet.get("defaultLanguage", "en"),
                    },
                    "status": {
                        "privacyStatus": status.get("privacyStatus", "public"),
                        "selfDeclaredMadeForKids": False,
                        "containsSyntheticMedia": True,  # ← AI label
                    },
                }
            ).execute()

            success += 1
            logger.info("[%d/%d] ✅ Labeled: %s — %s",
                i+1, len(all_video_ids), video_id, snippet["title"][:50])

        except Exception as e:
            failed += 1
            logger.error("[%d/%d] ❌ Failed: %s — %s",
                i+1, len(all_video_ids), video_id, str(e)[:100])

        # Small delay to avoid quota issues
        import time
        time.sleep(0.5)

    logger.info("=" * 50)
    logger.info("DONE: %d labeled ✅ | %d failed ❌", success, failed)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
