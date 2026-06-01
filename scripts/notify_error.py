"""
Error Notifier — sends error message to Telegram if pipeline fails.
Called by GitHub Actions on failure.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def send_error_to_telegram(error_msg: str):
    from telegram import Bot

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.error("Telegram credentials not set")
        return

    bot = Bot(token=token)
    async with bot:
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ *FitFacts Pipeline Failed!*\n\n"
                 f"🕐 Time: {os.getenv('GITHUB_RUN_ID', 'unknown')}\n"
                 f"🔗 Logs: https://github.com/Raj4478/fitness-pipeline/actions\n\n"
                 f"*Error:*\n```\n{error_msg[:800]}\n```\n\n"
                 f"Check Actions tab for full logs.",
            parse_mode="Markdown"
        )
    logger.info("Error notification sent to Telegram")


def get_error_from_logs() -> str:
    """Read last error from pipeline logs."""
    log_dir = Path("logs")
    if not log_dir.exists():
        return "No logs found — check GitHub Actions tab"
    logs = sorted(log_dir.glob("pipeline_*.log"), reverse=True)
    if not logs:
        return "No pipeline log found"
    try:
        content = logs[0].read_text()
        # Get last 20 lines
        lines = content.strip().split("\n")
        return "\n".join(lines[-20:])
    except Exception as e:
        return f"Could not read log: {e}"


def main():
    # Get error from command line arg or logs
    if len(sys.argv) > 1:
        error_msg = " ".join(sys.argv[1:])
    else:
        error_msg = get_error_from_logs()

    asyncio.run(send_error_to_telegram(error_msg))


if __name__ == "__main__":
    main()
