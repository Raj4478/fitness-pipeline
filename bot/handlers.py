"""
Telegram Bot Handlers — all command logic lives here.
"""

import logging
import os
import json
import urllib.request
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from bot.pipeline_runner import run_pipeline_async
from config.topics import TOPICS, WEEKLY_TOPICS

GITHUB_TOKEN = os.getenv("GH_ACTIONS_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "Raj4478/fitness-pipeline")
GITHUB_DEFAULT_BRANCH = os.getenv("GITHUB_DEFAULT_BRANCH", "master")

def _trigger_github_workflow(topic: str = "", workflow: str = "telegram_bot.yml") -> bool:
    """Trigger GitHub Actions workflow via API."""
    if not GITHUB_TOKEN:
        return False
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/dispatches"
        payload = {
            "ref": GITHUB_DEFAULT_BRANCH,
            "inputs": {
                "topic": topic,
                "command": "generate"
            }
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.github+json",
            },
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            return resp.status == 204
    except Exception as e:
        logger.error("GitHub trigger failed: %s", e)
        return False

logger = logging.getLogger(__name__)

ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))

TOPIC_LIST = TOPICS["fitness"]
TOPICS_PER_DAY = 3

WEEK_SCHEDULE = [
    (idx // TOPICS_PER_DAY + 1, topic)
    for idx, topic in enumerate(WEEKLY_TOPICS["fitness"])
]


def _auth(update: Update) -> bool:
    """Check if user is allowed."""
    uid = update.effective_user.id
    if ALLOWED_USER_ID and uid != ALLOWED_USER_ID:
        logger.warning("Unauthorized access attempt from user_id=%d", uid)
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update): return
    await update.message.reply_text(
        "🏋️ *FitFacts Pipeline Bot*\n\n"
        "Commands:\n"
        "`/generate <topic>` — generate specific topic\n"
        "`/generate` — auto-pick topic\n"
        "`/week` — generate all 21 videos\n"
        "`/topics` — show all topics\n"
        "`/status` — pipeline status\n"
        "`/help` — show this menu",
        parse_mode="Markdown"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update): return
    topic_list = "\n".join([f"{i+1}. {t}" for i, t in enumerate(TOPIC_LIST)])
    await update.message.reply_text(
        f"📋 *Available Topics:*\n\n{topic_list}\n\n"
        f"Use: `/generate protein myths`",
        parse_mode="Markdown"
    )


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update): return

    # Parse topic from command args
    topic = " ".join(context.args) if context.args else ""
    topic_display = topic or "auto-selected"

    await update.message.reply_text(
        f"⏳ Generating video for: *{topic_display}*\n"
        f"This takes ~45 seconds...",
        parse_mode="Markdown"
    )

    try:
        result = await run_pipeline_async(
            niche="fitness",
            topic=topic,
            dry_run=True,
        )

        if result["status"] == "success" and result["video_path"]:
            video_path = Path(result["video_path"])

            await update.message.reply_text(
                f"✅ *Video ready!*\n"
                f"Hook: _{result.get('hook', 'N/A')}_\n"
                f"File: `{video_path.name}`",
                parse_mode="Markdown"
            )

            # Send the video file
            if video_path.exists():
                await update.message.reply_text("📤 Sending video...")
                with open(video_path, "rb") as vf:
                    await update.message.reply_video(
                        video=vf,
                        caption=f"🏋️ *{topic_display}*\n\nReview and post manually or use /publish",
                        parse_mode="Markdown",
                    )
            else:
                await update.message.reply_text(
                    f"⚠️ Video file not found at: {video_path}"
                )
        else:
            await update.message.reply_text(
                f"❌ Pipeline failed!\n\nLog:\n```\n{result['log'][-500:]}\n```",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.exception("Pipeline error")
        await update.message.reply_text(f"❌ Error: {str(e)[:300]}")


async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update): return

    await update.message.reply_text(
        "📅 *Week Generation Started!*\n"
        "21 videos — this will take ~15 minutes.\n"
        "I'll update you after each video ✅",
        parse_mode="Markdown"
    )

    success = 0
    failed = 0

    for day, topic in WEEK_SCHEDULE:
        await update.message.reply_text(
            f"⏳ Day {day}: *{topic}*...",
            parse_mode="Markdown"
        )
        try:
            result = await run_pipeline_async(
                niche="fitness",
                topic=topic,
                dry_run=True,
            )
            if result["status"] == "success":
                success += 1
                await update.message.reply_text(
                    f"✅ Day {day}: *{topic}*\n"
                    f"_{result.get('hook', '')[:60]}_",
                    parse_mode="Markdown"
                )
            else:
                failed += 1
                await update.message.reply_text(
                    f"❌ Day {day}: *{topic}* failed",
                    parse_mode="Markdown"
                )
        except Exception as e:
            failed += 1
            await update.message.reply_text(f"❌ Error on {topic}: {str(e)[:100]}")

    await update.message.reply_text(
        f"🎉 *Week complete!*\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n\n"
        f"Check `tmp/videos/` for all files.",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update): return

    videos_dir = Path("tmp/videos")
    if videos_dir.exists():
        videos = list(videos_dir.glob("*.mp4"))
        count = len(videos)
        latest = max(videos, key=lambda f: f.stat().st_mtime).name if videos else "None"
    else:
        count = 0
        latest = "None"

    await update.message.reply_text(
        f"📊 *Pipeline Status*\n\n"
        f"Videos generated: `{count}`\n"
        f"Latest: `{latest}`\n"
        f"Storage: `tmp/videos/`",
        parse_mode="Markdown"
    )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Unknown command. Use /help to see all commands."
    )
