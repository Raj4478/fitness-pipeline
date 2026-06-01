"""
Telegram Webhook Server — runs on GitHub Actions
Polls Telegram for new messages and triggers workflows.
No laptop needed — runs entirely on GitHub Actions.
"""

import json
import logging
import os
import time
import urllib.request
import urllib.parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
GH_TOKEN = os.environ.get("GH_ACTIONS_TOKEN", "")
GH_REPO = "Raj4478/fitness-pipeline"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def api_call(method: str, payload: dict) -> dict:
    url = f"{BASE_URL}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def send_message(chat_id: int, text: str):
    api_call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})


def get_updates(offset: int = 0) -> list:
    try:
        result = api_call("getUpdates", {
            "offset": offset,
            "timeout": 10,
            "allowed_updates": ["message"]
        })
        return result.get("result", [])
    except Exception as e:
        logger.error("getUpdates failed: %s", e)
        return []


def trigger_workflow(topic: str = "") -> bool:
    if not GH_TOKEN:
        return False
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/actions/workflows/telegram_bot.yml/dispatches"
        payload = {"ref": "master", "inputs": {"topic": topic, "command": "generate"}}
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
        with urllib.request.urlopen(req) as resp:
            return resp.status == 204
    except Exception as e:
        logger.error("Workflow trigger failed: %s", e)
        return False


def handle_message(message: dict):
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "").strip()

    if user_id != ALLOWED_USER_ID:
        logger.warning("Unauthorized user: %s", user_id)
        return

    logger.info("Message from %s: %s", user_id, text)

    if text == "/start" or text == "/help":
        send_message(chat_id,
            "🏋️ *FitFacts Bot*\n\n"
            "`/generate <topic>` — generate video\n"
            "`/generate` — auto topic\n"
            "`/week` — generate full week\n"
            "`/topics` — show all topics\n"
            "`/status` — bot status"
        )

    elif text.startswith("/generate"):
        topic = text.replace("/generate", "").strip()
        topic_display = topic or "auto"
        send_message(chat_id,
            f"⏳ Triggering pipeline for: *{topic_display}*\n"
            f"Video will arrive in ~3 minutes 🎬"
        )
        ok = trigger_workflow(topic=topic)
        if ok:
            send_message(chat_id, f"✅ *Pipeline triggered!*\nTopic: _{topic_display}_")
        else:
            send_message(chat_id, "❌ Trigger failed — check GH_ACTIONS_TOKEN secret")

    elif text == "/week":
        topics = [
            "protein myths", "vitamin D deficiency india", "sitting disease office workers",
            "sleep and muscle growth", "sugar free drinks danger", "walking vs running",
            "creatine facts", "intermittent fasting facts", "gym myths busted",
            "cardio vs weight training", "stress and belly fat", "overtraining signs",
            "morning workout vs evening", "hydration myths", "BMI is misleading",
            "indian diet protein sources", "gut health india", "cold water after workout myth",
            "processed food addiction", "yoga science benefits", "protein myths"
        ]
        send_message(chat_id, f"📅 Triggering *21 videos*...\nEach will arrive separately on Telegram ✅")
        success = 0
        for topic in topics:
            if trigger_workflow(topic=topic):
                success += 1
            time.sleep(3)
        send_message(chat_id, f"🎉 *Done!* {success}/21 triggered successfully.")

    elif text == "/topics":
        topics_list = [
            "protein myths", "vitamin D deficiency india", "sitting disease",
            "sleep and muscle growth", "sugar free drinks", "walking vs running",
            "creatine facts", "intermittent fasting", "gym myths",
            "cardio vs weights", "stress and belly fat", "overtraining",
            "morning vs evening workout", "hydration myths", "BMI myths",
            "indian diet protein", "gut health", "cold water myth",
            "processed food", "yoga science"
        ]
        msg = "📋 *Topics:*\n\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics_list))
        send_message(chat_id, msg)

    elif text == "/status":
        send_message(chat_id,
            "📊 *Status*\n\n"
            "✅ Bot: Online\n"
            "✅ Schedule: 7AM, 1PM, 9PM IST\n"
            f"🔗 Repo: github.com/{GH_REPO}"
        )

    else:
        send_message(chat_id, "❓ Unknown command. Use /help")


def main():
    logger.info("Telegram webhook polling started (60 second window)")
    offset = 0
    start_time = time.time()

    # Poll for 55 seconds (GitHub Actions step limit safe)
    while time.time() - start_time < 55:
        updates = get_updates(offset=offset)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message")
            if message:
                handle_message(message)
        time.sleep(2)

    logger.info("Polling window complete")


if __name__ == "__main__":
    main()
