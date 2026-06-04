"""
Upload 13-second Short to YouTube.
Uses same credentials as main upload script.
"""

import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

def main():
    video_path = Path(os.environ.get("SHORT_VIDEO_PATH", ""))
    hook = os.environ.get("SHORT_HOOK", "Fitness Fact")
    topic = os.environ.get("SHORT_TOPIC", "fitness")

    if not video_path.exists():
        logger.error("Short video not found: %s", video_path)
        sys.exit(1)

    # Build title — hook + #shorts
    hook_clean = hook.replace('"', '').replace("'", "")[:80]
    title = f"{hook_clean} #shorts #fitness #india"
    if len(title) > 100:
        title = title[:97] + "..."

    description = (
        f"{hook}\n\n"
        f"Daily fitness facts in Hinglish — science-backed content for Indian Gen Z.\n\n"
        f"Follow @fitfacts.india on Instagram for carousel posts!\n\n"
        f"#fitness #fitnessfacts #indianfitness #shorts #gym #fitfactsindia"
    )

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials(
            token=None,
            refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN"),
            client_id=os.environ.get("YOUTUBE_CLIENT_ID"),
            client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
        )
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["fitness facts", "shorts", "indian fitness", "gym",
                         "hinglish", "fitfactsindia", "workout"],
                "categoryId": "17",
                "defaultLanguage": "hi",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024,
        )
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            _, response = request.next_chunk()

        video_id = response["id"]
        url = f"https://youtube.com/shorts/{video_id}"
        logger.info("✅ 13-sec Short uploaded: %s", url)
        print(url)

    except Exception as e:
        logger.error("YouTube upload failed: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
