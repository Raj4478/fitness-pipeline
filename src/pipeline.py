"""
Content Automation Pipeline — Main Orchestrator
Enhanced logging for root cause analysis.
"""

import asyncio
import logging
import sys
import traceback
import platform
import os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime:
    """Return current time in IST."""
    return datetime.now(IST)
from pathlib import Path
from typing import Optional

from src.generators.script_generator import ScriptGenerator
from src.generators.video_asset_fetcher import VideoAssetFetcher
from src.renderers.voice_generator import VoiceGenerator
from src.renderers.local_video_renderer import LocalVideoRenderer as VideoRenderer
from src.publishers.buffer_publisher import BufferPublisher
from src.storage.uploader import MediaUploader
from src.storage.run_tracker import RunTracker
from config.settings import Settings
from config.topics import TopicBank

logger = logging.getLogger(__name__)


def _is_public_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def log_system_info():
    """Log system environment for debugging."""
    logger.info("=" * 60)
    logger.info("SYSTEM INFO")
    logger.info("=" * 60)
    logger.info("OS: %s %s", platform.system(), platform.release())
    logger.info("Python: %s", sys.version)
    logger.info("CWD: %s", os.getcwd())
    logger.info("Runner: %s", os.getenv("RUNNER_NAME", "local"))
    logger.info("GitHub Run ID: %s", os.getenv("GITHUB_RUN_ID", "N/A"))
    logger.info("GitHub Run #: %s", os.getenv("GITHUB_RUN_NUMBER", "N/A"))

    # Check critical env vars (masked)
    critical_keys = [
        "GROQ_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY",
        "ELEVENLABS_API_KEY_2", "ELEVENLABS_API_KEY_3",
        "PEXELS_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USER_ID",
        "YOUTUBE_CLIENT_ID", "YOUTUBE_REFRESH_TOKEN"
    ]
    logger.info("-" * 40)
    logger.info("ENV VARS CHECK:")
    for key in critical_keys:
        val = os.getenv(key, "")
        if val:
            masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
            logger.info("  %-35s ✅ SET (%s)", key, masked)
        else:
            logger.warning("  %-35s ❌ MISSING", key)
    logger.info("=" * 60)


async def _notify_tts_provider(settings, provider_info: dict):
    """Send a separate Telegram notification about which TTS provider was used."""
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
    if not token or not chat_id:
        return
    try:
        provider = provider_info.get("provider", "unknown")
        model = provider_info.get("model", "unknown")
        voice_id = provider_info.get("voice_id", "N/A")
        key_idx = provider_info.get("key_index", "N/A")

        if provider == "elevenlabs":
            msg = (
                f"🎙 TTS Provider: ElevenLabs\n"
                f"   Model: {model}\n"
                f"   Voice ID: ...{str(voice_id)[-6:]}\n"
                f"   Key used: #{key_idx}"
            )
        else:
            msg = (
                f"⚠️ TTS Provider: gTTS Fallback\n"
                f"   Model: {model}\n"
                f"   Reason: All ElevenLabs keys exhausted\n"
                f"   Action needed: Check/renew ElevenLabs API keys"
            )

        import urllib.request, json
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("TTS provider notification sent")
    except Exception as e:
        logger.warning("TTS notification failed (non-critical): %s", e)


async def run_pipeline(
    niche: str,
    topic: Optional[str] = None,
    dry_run: bool = False,
    settings: Optional[Settings] = None,
) -> dict:
    tracker = RunTracker()
    run_id = tracker.start_run(niche)
    settings = settings or Settings()

    logger.info("=" * 60)
    logger.info("RUN %s STARTED | niche=%s dry_run=%s", run_id, niche, dry_run)
    logger.info("=" * 60)

    try:
        # ── 1. Topic ───────────────────────────────────────────────────
        logger.info("[1/7] Selecting topic...")
        topic_bank = TopicBank()
        selected_topic = topic or topic_bank.pick_unused(niche)
        logger.info("[1/7] ✅ Topic: %s", selected_topic)

        # ── 2. Script ──────────────────────────────────────────────────
        logger.info("[2/7] Generating script via LLM...")
        generator = ScriptGenerator(settings)
        script = await generator.generate(niche=niche, topic=selected_topic)
        logger.info("[2/7] ✅ Script generated | hook=%s", script.hook[:60])
        logger.info("       body preview: %s...", script.body[:80])

        # ── 3. Video asset ─────────────────────────────────────────────
        logger.info("[3/7] Fetching Pexels footage...")
        fetcher = VideoAssetFetcher(settings)
        video_asset = await fetcher.fetch(
            topic=selected_topic,
            visual_query=script.visual_query
        )
        logger.info("[3/7] ✅ Footage: %s", video_asset.url)

        # ── 4. Voiceover ───────────────────────────────────────────────
        logger.info("[4/7] Generating voiceover via ElevenLabs...")
        voice_gen = VoiceGenerator(settings)
        audio_path = await voice_gen.generate(
            text=script.tts_text,
            topic=selected_topic,
        )
        logger.info("[4/7] ✅ Audio: %s (%.1f KB)",
            audio_path, audio_path.stat().st_size / 1024)

        # ── 5. Render ──────────────────────────────────────────────────
        logger.info("[5/7] Rendering video with ffmpeg...")
        renderer = VideoRenderer(settings)
        render_result = await renderer.render(
            template_id="",
            hook_text=script.hook,
            body_text=script.body,
            video_url=video_asset.url,
            audio_url=str(audio_path),
            topic=selected_topic,
            subject=selected_topic,
        )
        logger.info("[5/7] ✅ Video: %s (%.1f MB)",
            render_result.video_url,
            Path(render_result.video_url).stat().st_size / (1024*1024))

        # ── 6. Publish ─────────────────────────────────────────────────
        post_ids = {}
        if not dry_run:
            logger.info("[6/7] Publishing...")
            publisher = BufferPublisher(settings)
            caption = script.build_caption(niche)
            publish_url = render_result.video_url
            if not _is_public_url(publish_url):
                video_path = Path(publish_url)
                if not video_path.exists():
                    logger.warning(
                        "[6/7] Rendered video not found at %s — skipping publish",
                        video_path,
                    )
                    publish_url = ""
                elif (
                    settings.cloudinary_cloud_name
                    and settings.cloudinary_api_key
                    and settings.cloudinary_api_secret
                ):
                    uploader = MediaUploader(settings)
                    publish_url = await uploader.upload_video(video_path)
                else:
                    logger.warning(
                        "[6/7] No public video URL and Cloudinary not configured — skipping publish"
                    )
                    publish_url = ""

            if publish_url:
                post_ids = await publisher.publish(
                    video_url=publish_url,
                    caption=caption,
                    channels=settings.buffer_channels,
                )
                logger.info("[6/7] ✅ Published | post_ids=%s", post_ids)
            else:
                logger.info("[6/7] ⏭️  Skipping publish — no public URL available")
        else:
            logger.info("[6/7] ⏭️  Dry run — skipping publish")

        # ── 7. Track ───────────────────────────────────────────────────
        logger.info("[7/7] Saving run record...")
        topic_bank.mark_used(niche, selected_topic)
        result = {
            "status": "success",
            "run_id": run_id,
            "niche": niche,
            "topic": selected_topic,
            "hook": script.hook,
            "video_url": render_result.video_url,
            "audio_url": str(audio_path),
            "post_ids": post_ids,
            "dry_run": dry_run,
            "timestamp": now_ist().isoformat(),
            "tts_provider": voice_provider,
        }
        tracker.complete_run(run_id, {
            "topic": selected_topic,
            "hook": script.hook,
            "video_url": render_result.video_url,
            "post_ids": post_ids,
        })
        logger.info("=" * 60)
        logger.info("RUN %s COMPLETE ✅", run_id)
        logger.info("  Video: %s", render_result.video_url)
        logger.info("  Hook:  %s", script.hook[:80])
        logger.info("=" * 60)
        return result

    except Exception as exc:
        # Full traceback with context
        tb = traceback.format_exc()
        logger.error("=" * 60)
        logger.error("RUN %s FAILED ❌", run_id)
        logger.error("Error type: %s", type(exc).__name__)
        logger.error("Error message: %s", str(exc))
        logger.error("-" * 40)
        logger.error("Full traceback:")
        for line in tb.split("\n"):
            if line.strip():
                logger.error("  %s", line)
        logger.error("=" * 60)

        # Save failed run
        try:
            tracker.fail_run(run_id, f"{type(exc).__name__}: {str(exc)}")
        except Exception:
            pass
        raise


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", default="fitness")
    parser.add_argument("--topic", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings()

    # Enhanced logging setup
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"pipeline_{now_ist().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    # Suppress noisy third-party loggers but keep errors
    for noisy in ["httpx", "httpcore", "urllib3", "googleapiclient"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Log system info at startup
    log_system_info()

    result = asyncio.run(
        run_pipeline(
            niche=args.niche,
            topic=args.topic or None,
            dry_run=args.dry_run,
            settings=settings,
        )
    )

    status = result.get("status", "unknown")
    video = result.get("video_url", "N/A")
    hook = result.get("hook", "N/A")
    print(f"\n{'✅' if status == 'success' else '❌'} Done | status={status}")
    print(f"   video: {video}")
    print(f"   hook:  {hook[:80]}")


if __name__ == "__main__":
    main()
