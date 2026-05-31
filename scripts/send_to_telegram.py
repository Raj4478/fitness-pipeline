"""
Telegram Sender — sends generated video + caption + hashtags
to your Telegram chat after pipeline runs.
Called by GitHub Actions after pipeline completes.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Hashtag sets — rotates daily
HASHTAG_SETS = [
    "#fitness #gym #gymmotivation #fitnessmotivation #reels #gymlife #fitfam #bodybuilding #workout #healthylifestyle #fitnessindia #indianfitness #proteinmyths #gymscience #fitfactsindia",
    "#fitness #gym #gymmotivation #fitnessmotivation #reels #fitnessjourney #gymrat #nutrition #muscle #weightloss #fitnessindia #indianhealth #vitamind #desifitness #fitfactsindia",
    "#fitness #gym #gymmotivation #fitnessmotivation #reels #workoutmotivation #strengthtraining #fitbody #gains #exercise #fitnessindia #indianfitness #officefitness #healthfacts #fitfactsindia",
    "#fitness #gym #gymmotivation #fitnessmotivation #reels #gymlife #fitfam #bodybuilding #workout #healthylifestyle #fitnessindia #musclegrowth #sleepscience #indiangym #fitfactsindia",
    "#fitness #gym #gymmotivation #fitnessmotivation #reels #fitnessjourney #gymrat #nutrition #muscle #weightloss #fitnessindia #healthfacts #sugarfree #indianhealth #fitfactsindia",
    "#fitness #gym #gymmotivation #fitnessmotivation #reels #workoutmotivation #strengthtraining #fitbody #gains #exercise #fitnessindia #cardio #walkvrun #desifitness #fitfactsindia",
    "#fitness #gym #gymmotivation #fitnessmotivation #reels #gymlife #fitfam #bodybuilding #workout #healthylifestyle #fitnessindia #creatine #gymscience #indiangym #fitfactsindia",
]

# Caption templates per topic
TOPIC_CAPTIONS = {
    "protein myths": "Yaar, tu roz 200g protein kha raha hai? Science kuch aur bol rahi hai.\n70kg insaan ko sirf 70g chahiye — WHO ka data hai ye.\nExtra protein fat banta hai, muscle nahi. Save karo ye video 🏋️",
    "vitamin d deficiency india": "India mein 76% log Vitamin D deficient hain — aur unhe pata bhi nahi.\nMuscle weakness, low testosterone, fatigue — sab iska result hai.\nSirf 20 min dhoop mein baitho — free solution 🌞",
    "sitting disease office workers": "8 ghante chair pe baithna = 47% zyada heart disease risk. Lancet study.\nGym karo ya na karo — sitting ka damage alag hota hai.\nHar ghante 5 min khade raho. Simple fix 💺",
    "sleep and muscle growth": "Gym toh karte ho — par neend 6 ghante?\n18% slower muscle growth hoti hai sleep deprivation mein.\n8 ghante neend = free muscle supplement 💤",
    "sugar free drinks danger": "Diet drink peete ho? WHO ne 2023 mein aspartame ko cancer risk flag kiya.\nZero calories = zero safety nahi hota.\nPaani piyo yaar. Seriously 🚨",
    "walking vs running": "Walking aur running mein calorie difference sirf 20% hai — Harvard study.\nSame distance = almost same burn. Knees bachao, walk karo.\nYe fact jaanta tha kya? 🚶",
    "creatine facts": "Creatine — 22 studies ka meta-analysis: 5-15% strength increase guaranteed.\nSabse zyada researched supplement hai ye.\n5g roz. Bas itna 💊",
    "intermittent fasting facts": "16:8 fasting ne insulin resistance 31% reduce ki — NEJM 2019 study.\nYe diet nahi, ye eating schedule hai.\nSubah ka breakfast skip karo — science hai iske peeche ⏰",
    "gym myths busted": "Roz gym jaao — galat hai ye. Muscle 48-72 ghante mein recover hoti hai.\nRoz same muscle = overtraining = zero results.\nRest day = growth day 🏋️",
    "cardio vs weight training": "Weights gym ke baad 24 ghante tak calories burn karta hai — EPOC effect.\nCardio sirf during workout burn karta hai.\nDono karo — par weights pehle 🔥",
    "stress and belly fat": "Stressed ho? Cortisol specifically belly fat store karta hai.\nGym karo par stress manage nahi kiya toh belly fat jayega nahi.\nSleep + meditation = flat stomach 😤",
    "overtraining signs": "Roz gym jaate ho aur results ruk gaye? Ye overtraining hai.\nBody repair ke liye time chahiye — without rest, muscle nahi banti.\nSigns: fatigue, mood swings, plateau 🚫",
    "morning workout vs evening": "Morning workout mein testosterone 20% zyada hota hai — study proved.\nEvening mein strength peak hoti hai — 3% better performance.\nJo consistently karo woh best hai ☀️",
    "hydration myths": "8 glasses paani roz — ye myth hai. Body weight ka 3% = actual need.\n70kg insaan = 2.1 liters. Zyada paani bhi harmful hota hai.\nThirst feel ho tab piyo 💧",
    "bmi is misleading": "BMI ne Virat Kohli ko overweight bola — seriously.\nMuscle fat se heavy hoti hai. BMI muscle aur fat ka fark nahi jaanta.\nBody fat % measure karo — BMI nahi 📊",
    "indian diet protein sources": "Indian khane mein protein nahi hota — myth tod do.\n100g paneer = 18g protein. 1 cup dahi = 10g.\nMeat zaruri nahi. Indian diet kafi hai 🥘",
    "gut health india": "Gut = second brain. 95% serotonin gut mein banta hai — brain mein nahi.\nPoor gut = poor mood + poor immunity + poor recovery.\nDahi, idli, kanji — Indian probiotics free mein hain 🦠",
    "cold water after workout myth": "Workout ke baad cold water mat piyo — ye myth hai.\nCold water core temperature fast regulate karta hai.\nRoom temperature slightly better hai — but cold water harmful nahi 🧊",
    "processed food addiction": "Processed food brain ke same receptors target karta hai jaise drugs — MIT study.\nUltra processed food = engineered addiction.\nLabel padho — 5 se zyada ingredients = processed 🍟",
    "yoga science benefits": "Yoga sirf stretching nahi — cortisol 20% reduce karta hai 8 weeks mein.\nHarvard ne bola yoga anxiety medication jitna effective hai.\nFlexibility + strength + mental health — ek saath 🧘",
}

DEFAULT_CAPTION = "Daily fitness fact — backed by science ✅\nSave karo aur share karo yaar 🏋️\n@fitfacts.india"


async def send_video_to_telegram(video_path: Path, caption: str, hashtags: str):
    """Send video to Telegram with caption and hashtags."""
    from telegram import Bot

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    bot = Bot(token=token)
    full_caption = f"{caption}\n\n{hashtags}"

    # Telegram caption limit is 1024 chars
    if len(full_caption) > 1024:
        full_caption = full_caption[:1020] + "..."

    logger.info("Sending video to Telegram: %s", video_path.name)

    async with bot:
        # Send notification first
        await bot.send_message(
            chat_id=chat_id,
            text=f"🎬 *New FitFacts Video Ready!*\n\n"
                 f"📁 File: `{video_path.name}`\n"
                 f"📊 Size: {video_path.stat().st_size // 1024}KB\n\n"
                 f"Sending video now...",
            parse_mode="Markdown"
        )

        # Send the video
        with open(video_path, "rb") as vf:
            await bot.send_video(
                chat_id=chat_id,
                video=vf,
                caption=full_caption,
                supports_streaming=True,
            )

        # Send caption separately for easy copy-paste
        await bot.send_message(
            chat_id=chat_id,
            text=f"📋 *Caption to copy:*\n\n{caption}\n\n{hashtags}",
            parse_mode="Markdown"
        )

    logger.info("Video sent successfully to Telegram")
    return True


def get_caption_and_hashtags() -> tuple[str, str]:
    """Get caption and hashtags based on latest generated video topic."""
    # Try to read topic from last run log
    topic = ""
    log_dir = Path("logs")
    if log_dir.exists():
        logs = sorted(log_dir.glob("pipeline_*.log"), reverse=True)
        if logs:
            try:
                content = logs[0].read_text()
                for line in content.split("\n"):
                    if "Topic selected:" in line:
                        topic = line.split("Topic selected:")[-1].strip().lower()
                        break
            except Exception:
                pass

    # Get matching caption
    caption = TOPIC_CAPTIONS.get(topic, DEFAULT_CAPTION)

    # Rotate hashtags based on day of week
    from datetime import datetime
    day_index = datetime.now().weekday() % len(HASHTAG_SETS)
    hashtags = HASHTAG_SETS[day_index]

    logger.info("Topic: %s | Caption length: %d", topic, len(caption))
    return caption, hashtags


async def main():
    # Find latest generated video
    videos_dir = Path("tmp/videos")
    if not videos_dir.exists():
        logger.error("No tmp/videos directory found")
        return

    videos = sorted(videos_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not videos:
        logger.error("No videos found in tmp/videos/")
        return

    latest_video = videos[0]
    logger.info("Latest video: %s", latest_video)

    caption, hashtags = get_caption_and_hashtags()
    await send_video_to_telegram(latest_video, caption, hashtags)


if __name__ == "__main__":
    asyncio.run(main())
