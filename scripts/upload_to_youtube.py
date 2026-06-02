"""
YouTube Shorts Auto-Uploader
Uploads generated fitness video to YouTube Shorts automatically.
Called by GitHub Actions after video generation.
"""

import logging
import os
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Topic → YouTube title + description + tags
TOPIC_YOUTUBE_DATA = {
    "protein myths": {
        "title": "70kg insaan ko sirf 70g protein chahiye — WHO Data #shorts #fitness",
        "description": "Kya tu roz 200g protein kha raha hai? WHO ke mutabiq 70kg insaan ko sirf 70g protein chahiye. Extra protein muscle nahi banta — fat banta hai!\n\n✅ Science-backed fitness facts daily\n🇮🇳 Hinglish fitness education\n\nFollow karein aur daily facts paaye!\n\n#proteinmyths #gymscience #fitnessfacts #indianfitness #fitfactsindia #shorts",
        "tags": ["protein myths", "gym science", "fitness facts", "indian fitness", "shorts", "hindi fitness"],
    },
    "vitamin d deficiency india": {
        "title": "India mein 76% log Vitamin D Deficient hain — ICMR Data #shorts",
        "description": "India mein 76% urban adults Vitamin D deficient hain — ICMR 2023 data. Low Vitamin D = low testosterone + weak muscles. Sirf 20 min subah ki dhoop kafi hai!\n\n✅ Daily fitness facts in Hinglish\n🇮🇳 Science-backed content\n\n#vitamind #indianhealth #fitnessfacts #fitfactsindia #shorts",
        "tags": ["vitamin d", "indian health", "fitness facts", "fitfacts india", "shorts"],
    },
    "sitting disease office workers": {
        "title": "8 Ghante Baithna = 47% Zyada Heart Risk — Lancet Study #shorts",
        "description": "Office mein 8 ghante baithte ho? Lancet study ke mutabiq ye 47% zyada heart disease risk hai — chahe gym karo ya na karo! Har ghante 5 min khade raho.\n\n✅ Daily fitness facts in Hinglish\n🇮🇳 Science-backed content\n\n#sittingdisease #officeworker #fitnessfacts #fitfactsindia #shorts",
        "tags": ["sitting disease", "office fitness", "fitness facts", "fitfacts india", "shorts"],
    },
    "sleep and muscle growth": {
        "title": "6 Ghante Neend = 18% Slow Muscle Growth — Study #shorts #gym",
        "description": "Gym karte ho but 6 ghante neend lete ho? Sleep Research Journal ke mutabiq muscle growth 18% slow hoti hai! Growth hormone sirf deep sleep mein release hota hai.\n\n✅ Daily fitness facts in Hinglish\n🇮🇳 Science-backed content\n\n#sleepscience #musclerecovery #gymfacts #fitfactsindia #shorts",
        "tags": ["sleep science", "muscle growth", "gym facts", "fitfacts india", "shorts"],
    },
    "sugar free drinks danger": {
        "title": "WHO ne Sugar-Free Drinks ko Cancer Risk Classify Kiya — 2023 #shorts",
        "description": "Diet Coke ya sugar-free drinks peete ho? WHO ne 2023 mein aspartame ko 'possibly carcinogenic' classify kiya. Zero calories matlab zero risk nahi!\n\n✅ Daily fitness facts in Hinglish\n🇮🇳 Science-backed content\n\n#sugarfreedrinks #healthfacts #aspartame #fitfactsindia #shorts",
        "tags": ["sugar free drinks", "health facts", "aspartame", "fitfacts india", "shorts"],
    },
    "walking vs running": {
        "title": "Walking vs Running — Calorie Fark Sirf 20% Hai — Harvard #shorts",
        "description": "Running karna zaruri nahi! Harvard study ke mutabiq same distance pe walking aur running mein sirf 20% calorie difference hai. 30 min walk se blood sugar 26% drop!\n\n✅ Daily fitness facts in Hinglish\n🇮🇳 Science-backed content\n\n#walkingbenefits #cardiotruth #fitnessfacts #fitfactsindia #shorts",
        "tags": ["walking benefits", "cardio truth", "fitness facts", "fitfacts india", "shorts"],
    },
    "creatine facts": {
        "title": "Creatine — 22 Studies ne Prove Kiya 5-15% Strength Increase #shorts",
        "description": "Creatine duniya ka sabse researched supplement hai — 22 studies ke meta-analysis mein 5-15% strength increase proven. Paani se bhi safe hai. Sirf 5g roz!\n\n✅ Daily fitness facts in Hinglish\n🇮🇳 Science-backed content\n\n#creatinefacts #gymscience #supplementtruth #fitfactsindia #shorts",
        "tags": ["creatine facts", "gym science", "supplement truth", "fitfacts india", "shorts"],
    },
    "intermittent fasting facts": {
        "title": "16:8 Fasting ne Insulin Resistance 31% Reduce Ki — NEJM 2019 #shorts",
        "description": "Intermittent fasting sirf trend nahi — NEJM 2019 study mein 16:8 fasting ne 12 weeks mein insulin resistance 31% reduce ki. Ye diet nahi, eating schedule hai!\n\n✅ Daily fitness facts in Hinglish\n🇮🇳 Science-backed content\n\n#intermittentfasting #fastingscience #dietfacts #fitfactsindia #shorts",
        "tags": ["intermittent fasting", "fasting science", "diet facts", "fitfacts india", "shorts"],
    },
    "gym myths busted": {
        "title": "Roz Gym Jaana Galat Hai — Muscle 48-72 Ghante Mein Recover Hoti Hai #shorts",
        "description": "Roz gym jaate ho? Muscle 48-72 ghante mein recover hoti hai — roz same muscle thao toh overtraining hoga. Rest day = growth day!\n\n✅ Daily fitness facts in Hinglish\n🇮🇳 Science-backed content\n\n#gymmyths #overtraining #restday #gymscience #fitfactsindia #shorts",
        "tags": ["gym myths", "overtraining", "rest day", "gym science", "fitfacts india", "shorts"],
    },
}

DEFAULT_YT_DATA = {
    "title": "Daily Fitness Fact — Science-Backed Hinglish Content #shorts #fitness #india",
    "description": "Daily fitness facts in Hinglish — science-backed content for Indian Gen Z.\n\n✅ No supplement ads\n✅ Real studies cited\n🇮🇳 Made for India\n\nFollow @fitfacts.india on Instagram!\n\n#fitness #fitnessfacts #indianfitness #shorts #gym",
    "tags": ["fitness facts", "indian fitness", "hinglish fitness", "shorts", "gym"],
}


def get_hook_from_logs() -> str:
    """Extract actual hook text from pipeline logs."""
    log_dir = Path("logs")
    if not log_dir.exists():
        return ""
    logs = sorted(log_dir.glob("pipeline_*.log"), reverse=True)
    if not logs:
        return ""
    try:
        content = logs[0].read_text()
        for line in content.split("\n"):
            if "hook=" in line:
                hook = line.split("hook=")[-1].strip()
                # Clean up hook for YouTube title
                for ch in ["*", "_", "`", "#"]:
                    hook = hook.replace(ch, "")
                return hook[:80].strip()
    except Exception:
        pass
    return ""


def build_title_from_hook(hook: str, topic: str) -> str:
    """Build YouTube title from hook + topic tags."""
    if not hook:
        return DEFAULT_YT_DATA["title"]
    # Add shorts tag if not present
    title = hook
    if "#shorts" not in title.lower():
        title = f"{title} #shorts"
    if "#fitness" not in title.lower():
        title = f"{title} #fitness"
    # YouTube title max 100 chars
    return title[:97] + "..." if len(title) > 100 else title


def get_youtube_service():
    """Build YouTube API service using refresh token."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN", "")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError("YouTube credentials not set in environment")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(video_path: Path, topic: str) -> str:
    """Upload video to YouTube Shorts. Returns video URL."""
    from googleapiclient.http import MediaFileUpload

    yt_data = TOPIC_YOUTUBE_DATA.get(topic, DEFAULT_YT_DATA)

    # Use actual hook from pipeline as title — much better CTR
    hook = get_hook_from_logs()
    if hook:
        final_title = build_title_from_hook(hook, topic)
        logger.info("Title from hook: %s", final_title)
    else:
        final_title = yt_data["title"]
        logger.info("Title from preset: %s", final_title)

    youtube = get_youtube_service()
    logger.info("Uploading to YouTube: %s", video_path.name)

    body = {
        "snippet": {
            "title": final_title[:100],  # YouTube title limit
            "description": yt_data["description"][:5000],
            "tags": yt_data["tags"],
            "categoryId": "17",  # Sports category
            "defaultLanguage": "hi",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024,  # 1MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("Upload progress: %d%%", int(status.progress() * 100))

    video_id = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}"
    logger.info("✅ Uploaded to YouTube: %s", video_url)
    return video_url


async def notify_telegram(video_url: str, video_path: Path, topic: str):
    """Send YouTube URL to Telegram."""
    from telegram import Bot

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    yt_data = TOPIC_YOUTUBE_DATA.get(topic, DEFAULT_YT_DATA)

    # Clean title — remove special chars that break Markdown
    hook = get_hook_from_logs() or yt_data['title']
    safe_title = hook[:80].replace('`', '').replace('*', '').replace('_', '').replace('[', '').replace(']', '')

    bot = Bot(token=token)
    async with bot:
        await bot.send_message(
            chat_id=chat_id,
            text=f"🎬 YouTube Shorts Uploaded!\n\n"
                 f"🔗 {video_url}\n\n"
                 f"📋 Title: {safe_title}\n\n"
                 f"✅ Live on YouTube now!",
            parse_mode=None
        )


def get_topic_from_logs() -> str:
    log_dir = Path("logs")
    if not log_dir.exists():
        return ""
    logs = sorted(log_dir.glob("pipeline_*.log"), reverse=True)
    if not logs:
        return ""
    try:
        content = logs[0].read_text()
        for line in content.split("\n"):
            if "Topic selected:" in line:
                return line.split("Topic selected:")[-1].strip().lower()
    except Exception:
        pass
    return ""


def main():
    import asyncio

    # Find latest shorts video
    shorts_dir = Path("tmp/shorts")
    videos_dir = Path("tmp/videos")

    # Prefer shorts version, fallback to main video
    for search_dir in [shorts_dir, videos_dir]:
        if search_dir.exists():
            videos = sorted(
                search_dir.glob("*.mp4"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            if videos:
                latest = videos[0]
                break
    else:
        logger.error("No videos found")
        return

    topic = get_topic_from_logs()
    logger.info("Uploading topic: %s | file: %s", topic, latest.name)

    try:
        video_url = upload_to_youtube(latest, topic)
        asyncio.run(notify_telegram(video_url, latest, topic))
    except Exception as e:
        logger.error("YouTube upload failed: %s", e)
        raise


if __name__ == "__main__":
    main()
