from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import yt_dlp
from yt_dlp.utils import DownloadError

MAX_TELEGRAM_BYTES = 49 * 1024 * 1024
BLOCKED_AVAILABILITY = {"private", "premium_only", "subscriber_only", "needs_auth"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
INSTAGRAM_REEL_PATH = re.compile(r"^/reels?/[^/]+/?$", re.IGNORECASE)


def send_text(token: str, chat_id: str, text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}},
        timeout=30,
    )
    response.raise_for_status()


def send_video(token: str, chat_id: str, path: Path, caption: str) -> None:
    with path.open("rb") as handle:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendVideo",
            data={"chat_id": chat_id, "caption": caption[:1000], "supports_streaming": "true"},
            files={"video": (path.name, handle, "video/mp4")},
            timeout=180,
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("ok") is not True:
        raise RuntimeError("telegram_upload_failed")


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise ValueError("invalid_media_url")
    if host in YOUTUBE_HOSTS:
        return "YouTube"
    if host in INSTAGRAM_HOSTS and INSTAGRAM_REEL_PATH.fullmatch(parsed.path):
        return "Instagram Reel"
    raise ValueError("invalid_media_url")


def inspect_media(url: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "geo_bypass": False,
        "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def download_at_height(url: str, directory: Path, height: int, provider: str) -> Path:
    output_template = str(directory / "%(id)s-%(height)sp.%(ext)s")
    if provider == "YouTube":
        format_selector = (
            f"bv*[height<={height}][vcodec^=avc1]+ba[acodec^=mp4a]/"
            f"b[height<={height}][vcodec^=avc1][ext=mp4]/"
            f"b[height<={height}][ext=mp4]"
        )
    else:
        format_selector = (
            f"b[height<={height}][ext=mp4]/"
            "best[ext=mp4]/"
            f"best[height<={height}]/best"
        )

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "geo_bypass": False,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "max_filesize": MAX_TELEGRAM_BYTES,
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "format": format_selector,
        "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    }
    before = set(directory.iterdir())
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])
    candidates = [p for p in directory.iterdir() if p not in before and p.is_file() and p.suffix.lower() == ".mp4"]
    if not candidates:
        candidates = [p for p in directory.glob("*.mp4") if p.is_file()]
    if not candidates:
        raise RuntimeError("download_output_missing")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main() -> int:
    url = os.environ.get("MEDIA_URL", os.environ.get("YOUTUBE_URL", "")).strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    allowed_user = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    max_duration = int(os.environ.get("DOWNLOAD_MAX_DURATION_SECONDS", "900"))

    if (
        not token
        or not re.fullmatch(r"\d+", chat_id)
        or not re.fullmatch(r"\d+", allowed_user)
        or chat_id != allowed_user
    ):
        print("worker configuration incomplete", file=sys.stderr)
        return 2

    try:
        provider = validate_url(url)
        send_text(token, chat_id, f"⬇️ {provider} download started. I’ll return the video here if it fits Telegram’s upload limit.")

        info = inspect_media(url)
        availability = str(info.get("availability") or "").lower()
        if availability in BLOCKED_AVAILABILITY:
            raise RuntimeError("access_restricted_video")
        if info.get("is_live"):
            raise RuntimeError("live_stream_not_supported")
        duration = int(info.get("duration") or 0)
        if duration and duration > max_duration:
            raise RuntimeError("video_too_long")

        with tempfile.TemporaryDirectory(prefix="telegram-ytdlp-") as temp:
            directory = Path(temp)
            last_error: Exception | None = None
            for height in (720, 480, 360):
                try:
                    for old in directory.iterdir():
                        if old.is_file():
                            old.unlink()
                    path = download_at_height(url, directory, height, provider)
                    if path.stat().st_size > MAX_TELEGRAM_BYTES:
                        last_error = RuntimeError("telegram_size_limit")
                        continue
                    title = str(info.get("title") or provider)[:180]
                    send_video(token, chat_id, path, f"✅ {title}\n{provider} · up to {height}p")
                    return 0
                except (DownloadError, RuntimeError) as error:
                    last_error = error
                    continue
            raise last_error or RuntimeError("download_failed")

    except Exception as error:
        reason = str(error)
        if reason == "video_too_long":
            message = "I couldn’t download this video because it exceeds the configured duration limit."
        elif reason == "live_stream_not_supported":
            message = "Live-stream downloading is not supported by this bot."
        elif reason == "access_restricted_video":
            message = "I won’t download private, members-only, premium, or sign-in-gated videos."
        elif reason == "telegram_size_limit":
            message = "I couldn’t get this video under Telegram’s current 50 MB bot upload limit, even at lower resolution."
        elif reason == "invalid_media_url":
            message = "Only supported public YouTube URLs and Instagram Reel URLs can be downloaded by this worker."
        else:
            message = "The download could not be completed. The Reel/video may be unavailable, require login, or be unsupported."
        try:
            send_text(token, chat_id, f"❌ {message}")
        except Exception:
            pass
        print("download worker failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
