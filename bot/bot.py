"""
Telegram Bot — main bot setup and registration.
"""

import logging
import os
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from bot.handlers import (
    start, help_cmd, generate, week, topics, status, unknown
)

logger = logging.getLogger(__name__)


def create_app() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN not set in .env\n"
            "Get it from @BotFather on Telegram"
        )

    app = Application.builder().token(token).build()

    # Register commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("generate", generate))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("topics", topics))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot handlers registered")
    return app
