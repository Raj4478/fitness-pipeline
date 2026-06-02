"""
Telegram Webhook — polls for new messages and triggers GitHub Actions.
Saves offset to file so messages are never missed or double-processed.
"""

import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.topics import TOPICS, WEEKLY_TOPICS

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
GH_TOKEN = os.environ.get("GH_ACTIONS_TOKEN", "")
GH_REPO = os.getenv("GITHUB_REPO", "Raj4478/fitness-pipeline")
GH_DEFAULT_BRANCH = os.getenv("GITHUB_DEFAULT_BRANCH", "master")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
OFFSET_FILE = Path(".telegram_offset")


def tg(method: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error("%s failed: %s", method, e)
        return {}


def send(chat_id: int, text: str):
    tg("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})


def get_updates(offset: int) -> list:
    result = tg("getUpdates", {"offset": offset, "timeout": 5, "limit": 10})
    return result.get("result", [])


def trigger_workflow(topic: str = "") -> bool:
    if not GH_TOKEN:
        logger.error("GH_ACTIONS_TOKEN not set")
        return False
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/telegram_bot.yml/dispatches"
        payload = {"ref": GH_DEFAULT_BRANCH, "inputs": {"topic": topic, "command": "generate"}}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Authorization": f"Bearer {GH_TOKEN}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.github+json",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            success = resp.status == 204
            logger.info("Workflow trigger: %s (topic=%s)", "OK" if success else "FAILED", topic)
            return success
    except Exception as e:
        logger.error("Workflow trigger error: %s", e)
        return False


def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except Exception:
            pass
    return 0


def save_offset(offset: int):
    OFFSET_FILE.write_text(str(offset))


def handle(chat_id: int, text: str):
    text = text.strip()
    logger.info("Handling command: %s", text)

    if text in ("/start", "/help"):
        send(chat_id,
            "🏋️ *FitFacts Bot*\n\n"
            "`/generate <topic>` — generate video\n"
            "`/generate` — auto topic\n"
            "`/week` — full week (21 videos)\n"
            "`/topics` — all topics\n"
            "`/status` — bot status"
        )

    elif text.startswith("/generate"):
        topic = text.replace("/generate", "").strip()
        topic_display = topic or "auto"
        send(chat_id, f"⏳ Triggering: *{topic_display}*\nVideo arrives in ~3 mins 🎬")
        ok = trigger_workflow(topic=topic)
        if ok:
            send(chat_id, f"✅ *Pipeline triggered!*\nTopic: _{topic_display}_\nSit back — video coming soon 🏋️")
        else:
            send(chat_id, "❌ Trigger failed\nCheck: GH\\_ACTIONS\\_TOKEN secret in GitHub")

    elif text == "/week":
        topics = WEEKLY_TOPICS["fitness"]
        send(chat_id, f"📅 Triggering *21 videos*...\nEach will arrive separately ✅")
        success = 0
        for topic in topics:
            if trigger_workflow(topic=topic):
                success += 1
            time.sleep(3)
        send(chat_id, f"🎉 *Done!* {success}/21 triggered successfully.")

    elif text == "/topics":
        topics_list = TOPICS["fitness"]
        msg = "📋 *Topics:*\n\n" + "\n".join(
            f"{i+1}. {t}" for i, t in enumerate(topics_list)
        )
        send(chat_id, msg)

    elif text == "/status":
        send(chat_id,
            "📊 *Status*\n\n"
            "✅ Bot: Online\n"
            "✅ Listener: Every 5 mins\n"
            "✅ Schedule: 7AM 1PM 9PM IST\n"
            f"🔗 `github.com/{GH_REPO}`"
        )

    else:
        send(chat_id, f"❓ Unknown: `{text[:30]}`\nUse /help")


def main():
    logger.info("Starting Telegram listener")
    offset = load_offset()
    logger.info("Starting from offset: %d", offset)

    updates = get_updates(offset)
    logger.info("Found %d updates", len(updates))

    for update in updates:
        update_id = update.get("update_id", 0)
        message = update.get("message", {})
        user_id = message.get("from", {}).get("id", 0)
        chat_id = message.get("chat", {}).get("id", 0)
        text = message.get("text", "")

        logger.info("Update %d: user=%d text=%s", update_id, user_id, text[:50])

        # Update offset first to avoid reprocessing
        save_offset(update_id + 1)
        offset = update_id + 1

        if user_id != ALLOWED_USER_ID:
            logger.warning("Ignored unauthorized user: %d", user_id)
            continue

        if text:
            handle(chat_id, text)

    logger.info("Listener run complete. Next offset: %d", offset)


if __name__ == "__main__":
    main()
