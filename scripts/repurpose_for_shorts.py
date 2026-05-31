"""
YouTube Shorts Repurposer
Takes the generated fitness video and creates a YouTube Shorts version.
- Trims to 59 seconds max (YouTube Shorts limit)
- Adds "SHORTS" watermark removed from outro
- Same video, zero extra work — double the audience
Called by GitHub Actions after main video is generated.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SHORTS_DIR = Path("tmp/shorts")
SHORTS_DIR.mkdir(parents=True, exist_ok=True)
MAX_SHORTS_DURATION = 59  # YouTube Shorts must be under 60 seconds


def get_ffmpeg():
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError("ffmpeg not found")


def get_duration(ffmpeg_path: str, video_path: Path) -> float:
    ffprobe = shutil.which("ffprobe") or str(Path(ffmpeg_path).parent / "ffprobe")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def create_shorts_version(video_path: Path) -> Path:
    """
    Creates YouTube Shorts version — trimmed to 59s max.
    Same 9:16 vertical format — no changes needed.
    """
    ffmpeg = get_ffmpeg()
    duration = get_duration(ffmpeg, video_path)

    shorts_path = SHORTS_DIR / f"shorts_{video_path.name}"

    if duration <= MAX_SHORTS_DURATION:
        # Already short enough — just copy
        logger.info("Video is %.1fs — within Shorts limit, copying as-is", duration)
        import shutil as sh
        sh.copy2(video_path, shorts_path)
    else:
        # Trim to 59 seconds
        logger.info("Video is %.1fs — trimming to %ds for Shorts", duration, MAX_SHORTS_DURATION)
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(video_path),
             "-t", str(MAX_SHORTS_DURATION),
             "-c", "copy",
             str(shorts_path)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg trim failed: {result.stderr[-300:]}")

    logger.info("Shorts version created: %s", shorts_path)
    return shorts_path


async def send_shorts_to_telegram(shorts_path: Path, topic: str):
    """Send Shorts version to Telegram with YouTube-specific caption."""
    from telegram import Bot

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("Telegram credentials not set — skipping Shorts send")
        return

    # YouTube Shorts caption — different from Instagram
    yt_caption = (
        f"🎬 *YouTube Shorts Version Ready!*\n\n"
        f"📁 `{shorts_path.name}`\n"
        f"⏱ Max 59 seconds — ready to upload\n\n"
        f"*YouTube title suggestion:*\n"
        f"`{topic.title()} — Fitness Facts India #shorts`\n\n"
        f"*YouTube description:*\n"
        f"Daily fitness facts in Hinglish 🏋️\n"
        f"Subscribe for more science-backed fitness content!\n"
        f"#shorts #fitness #fitnessfacts #gym #india"
    )

    bot = Bot(token=token)
    async with bot:
        with open(shorts_path, "rb") as vf:
            await bot.send_video(
                chat_id=chat_id,
                video=vf,
                caption=yt_caption,
                parse_mode="Markdown",
                supports_streaming=True,
            )
    logger.info("Shorts sent to Telegram ✅")


def main():
    import asyncio

    videos_dir = Path("tmp/videos")
    if not videos_dir.exists():
        logger.error("No tmp/videos directory")
        return

    videos = sorted(
        videos_dir.glob("*.mp4"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not videos:
        logger.error("No videos found")
        return

    latest = videos[0]
    topic = latest.stem.replace("_", " ").rsplit(" ", 1)[0]  # Remove run ID

    shorts_path = create_shorts_version(latest)
    asyncio.run(send_shorts_to_telegram(shorts_path, topic))


if __name__ == "__main__":
    main()
