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
from datetime import datetime
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


async def run_pipeline(
    niche: str,
    topic: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    run_id = f"{niche[:3]}{datetime.utcnow().strftime('%H%M%S%f')[:10]}"
    tracker = RunTracker()
    settings = Settings()

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
            post_ids = await publisher.publish(
                video_path=Path(render_result.video_url),
                caption=caption,
            )
            logger.info("[6/7] ✅ Published | post_ids=%s", post_ids)
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
            "timestamp": datetime.utcnow().isoformat(),
        }
        tracker.save(result)
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
        tracker.save({
            "status": "failed",
            "run_id": run_id,
            "niche": niche,
            "topic": topic or "unknown",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": tb,
            "timestamp": datetime.utcnow().isoformat(),
        })
        raise


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--niche", default="fitness")
    parser.add_argument("--topic", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Enhanced logging setup
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"pipeline_{datetime.utcnow().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.DEBUG,
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
