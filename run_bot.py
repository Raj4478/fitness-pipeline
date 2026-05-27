"""
Entry point — run the Telegram bot.

Usage:
    python run_bot.py

Setup:
    1. Add to .env:
       TELEGRAM_BOT_TOKEN=your_token_from_botfather
       TELEGRAM_ALLOWED_USER_ID=your_telegram_user_id

    2. Install deps:
       pip install python-telegram-bot

    3. Run:
       python run_bot.py
"""

import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("logs") / "bot.log"),
    ],
)

logger = logging.getLogger(__name__)


def main():
    from bot.bot import create_app
    logger.info("Starting FitFacts Telegram Bot...")
    app = create_app()
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
