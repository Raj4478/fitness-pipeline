"""
Telegram Sender — sends generated video + keyword-rich caption + 
optimised 5 hashtags to Telegram after pipeline runs.
Called by GitHub Actions after pipeline completes.
"""

import asyncio
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── 5 hashtags per topic — optimised for Instagram 2026 ───────────────────────
TOPIC_HASHTAGS = {
    "protein myths":                "#proteinmyths #gymscience #fitnessfacts #indianfitness #fitfactsindia",
    "vitamin d deficiency india":   "#vitaminddeficiency #indianhealth #fitnessfacts #sunlighthealth #fitfactsindia",
    "sitting disease office workers":"#sittingdisease #officeworker #fitnessfacts #deskjob #fitfactsindia",
    "sleep and muscle growth":      "#sleepscience #musclerecovery #gymfacts #sleephealth #fitfactsindia",
    "sugar free drinks danger":     "#sugarfreedrinks #healthfacts #aspartame #dietdrink #fitfactsindia",
    "walking vs running":           "#walkingbenefits #cardiotruth #fitnessfacts #calorieburn #fitfactsindia",
    "creatine facts":               "#creatinefacts #gymscience #supplementtruth #strengthtraining #fitfactsindia",
    "intermittent fasting facts":   "#intermittentfasting #fastingscience #insulinresistance #dietfacts #fitfactsindia",
    "gym myths busted":             "#gymmyths #overtraining #restday #gymscience #fitfactsindia",
    "cardio vs weight training":    "#cardiovsweights #epoeffect #fatburn #gymscience #fitfactsindia",
    "stress and belly fat":         "#cortisol #bellyfat #stressfat #fitnessfacts #fitfactsindia",
    "overtraining signs":           "#overtraining #musclerecovery #gymrest #fitnessfacts #fitfactsindia",
    "morning workout vs evening":   "#morningworkout #workouttime #testosterone #gymscience #fitfactsindia",
    "hydration myths":              "#hydrationmyths #waterintake #fitnessfacts #healthtips #fitfactsindia",
    "bmi is misleading":            "#bmimyth #bodycomposition #fitnessfacts #bodyfat #fitfactsindia",
    "indian diet protein sources":  "#indiandiet #vegetarianprotein #paneer #fitnessindia #fitfactsindia",
    "gut health india":             "#guthealth #microbiome #indianprobiotics #healthfacts #fitfactsindia",
    "cold water after workout myth":"#coldwatermyth #postworkout #gymmyths #fitnessfacts #fitfactsindia",
    "processed food addiction":     "#processedfood #foodaddiction #ultraprocessed #healthfacts #fitfactsindia",
    "yoga science benefits":        "#yogascience #cortisol #mentalhealth #yogafacts #fitfactsindia",
}

DEFAULT_HASHTAGS = "#fitnessfacts #gymscience #indianfitness #healthfacts #fitfactsindia"

# ── Keyword-rich captions per topic ───────────────────────────────────────────
# Written with natural language keywords Instagram's AI reads
TOPIC_CAPTIONS = {
    "protein myths": (
        "70kg insaan ko sirf 70g protein chahiye — WHO ka data.\n"
        "Tu roz 200g kha raha hai? Extra protein muscle nahi banta, fat banta hai.\n"
        "1 cup dahi + 3 eggs + 100g chicken = full day protein sorted.\n"
        "Ye protein myth tod do aur apne gym bro ko bhi batao 🏋️\n"
        "Save karo — baad mein kaam aayega 💾"
    ),
    "vitamin d deficiency india": (
        "India mein 76% urban log Vitamin D deficient hain — ICMR 2023 data.\n"
        "Kam Vitamin D = low testosterone + weak muscles + fatigue.\n"
        "Sirf 20 min subah ki dhoop kafi hai — bilkul free supplement.\n"
        "Agar gym results ruk gaye hain toh pehle Vitamin D test karo 🌞\n"
        "Share karo yaar — ye sab ko pata hona chahiye 💾"
    ),
    "sitting disease office workers": (
        "8 ghante chair pe baithna = 47% zyada heart disease risk — Lancet study.\n"
        "Gym karo ya na karo — prolonged sitting ka damage alag hota hai.\n"
        "Har ghante sirf 5 min khade raho — risk dramatically drops.\n"
        "Office job hai? Ye ek change karo aaj se 💺\n"
        "Save karo aur apne office friends ko tag karo 💾"
    ),
    "sleep and muscle growth": (
        "6 ghante neend le rahe ho? Muscle growth 18% slow hoti hai — Sleep Research Journal.\n"
        "Growth hormone sirf deep sleep mein release hota hai — gym ke baad nahi.\n"
        "8 ghante neend = sabse powerful free muscle supplement.\n"
        "Gym se zyada important hai tera pillow 😴\n"
        "Save karo — ye fact bahut log ignore karte hain 💾"
    ),
    "sugar free drinks danger": (
        "Diet Coke ya sugar-free drinks peete ho? Sunlo ye.\n"
        "WHO ne 2023 mein aspartame ko 'possibly carcinogenic' classify kiya.\n"
        "Zero calories matlab zero risk nahi hota — ye myth hai.\n"
        "Paani mein nimbu daalo — taste bhi, health bhi 🚨\n"
        "Share karo — logo ko ye pata hona chahiye 💾"
    ),
    "walking vs running": (
        "Running karna zaruri nahi — walking se bhi same distance pe almost same calories burn.\n"
        "Harvard study: difference sirf 20% hai calorie burn mein.\n"
        "30 min walk se blood sugar 26% drop hoti hai — diabetics ke liye gold.\n"
        "Knees bachao, walk karo, results lo 🚶\n"
        "Save karo aur apne parents ko bhi share karo 💾"
    ),
    "creatine facts": (
        "Creatine — 22 studies ka meta-analysis ne prove kiya: 5-15% strength increase.\n"
        "Sabse zyada researched supplement in the world — paani se bhi safe.\n"
        "Sirf 5g roz, kisi bhi time pe, bina loading phase ke.\n"
        "Creatine ke baare mein jo myths hain — sab galat hain 💊\n"
        "Save karo — gym bro ko facts dene ka time aa gaya 💾"
    ),
    "intermittent fasting facts": (
        "16:8 intermittent fasting ne 12 weeks mein insulin resistance 31% reduce ki — NEJM 2019.\n"
        "Ye diet nahi hai — ye ek eating schedule hai.\n"
        "8-hour window mein kuch bhi khao — results aate hain.\n"
        "Subah ka breakfast skip karna actually science-backed hai ⏰\n"
        "Save karo — ye method try karna ho toh pehle ye padho 💾"
    ),
    "gym myths busted": (
        "Roz gym jaana = better results? Galat.\n"
        "Muscle 48-72 ghante mein recover hoti hai — roz same muscle mat thao.\n"
        "Rest day pe body zyada muscle banati hai — workout ke time nahi.\n"
        "Smart training > hard training. Rest day = growth day 🏋️\n"
        "Save karo aur apne gym partner ko tag karo 💾"
    ),
    "cardio vs weight training": (
        "Cardio sirf workout ke time calories burn karta hai.\n"
        "Weights gym ke baad 24 ghante tak burn karte hain — EPOC effect.\n"
        "Same session length mein weights = 2x total calorie burn.\n"
        "Fat loss ke liye weights pehle, cardio baad mein 🔥\n"
        "Save karo — ye order matter karta hai 💾"
    ),
    "stress and belly fat": (
        "Stressed ho aur belly fat nahi ja raha? Cortisol ki wajah se hai ye.\n"
        "High cortisol specifically belly fat store karta hai — arms ya legs mein nahi.\n"
        "Gym karo but stress manage nahi kiya toh belly fat kabhi nahi jayega.\n"
        "Sleep + meditation + workout = flat stomach formula 😤\n"
        "Save karo — ye connection bahut log miss karte hain 💾"
    ),
    "overtraining signs": (
        "Roz gym ja rahe ho aur results plateau ho gaye? Ye overtraining hai.\n"
        "Signs: constant fatigue, mood swings, strength drop, poor sleep.\n"
        "Body ko repair time chahiye — without rest, muscle nahi banti.\n"
        "Ek week ka deload lo — agle week PR hit karoge 🚫\n"
        "Save karo — ye signs ignore mat karo 💾"
    ),
    "morning workout vs evening": (
        "Morning workout mein testosterone 20% zyada hota hai — study proved.\n"
        "Evening mein core body temperature peak hoti hai — 3% better strength.\n"
        "Dono sahi hain — jo consistently karo woh best hai.\n"
        "Best workout time = jo time tum actually karo 🏃\n"
        "Save karo aur apna preferred time comments mein batao 💾"
    ),
    "hydration myths": (
        "8 glasses paani roz — ye myth hai. Koi science nahi hai iske peeche.\n"
        "Actual formula: body weight (kg) x 0.033 = daily liters.\n"
        "70kg insaan = 2.3 liters. Zyada paani bhi harmful — hyponatremia.\n"
        "Thirst feel ho tab piyo — body ka signal trust karo 💧\n"
        "Save karo — ye formula note karo 💾"
    ),
    "bmi is misleading": (
        "BMI ne Virat Kohli ko overweight classify kiya — seriously.\n"
        "BMI sirf height aur weight dekhta hai — muscle aur fat ka fark nahi karta.\n"
        "Bodybuilder aur obese person ka BMI same ho sakta hai.\n"
        "Body fat percentage measure karo — BMI ek outdated metric hai 📊\n"
        "Save karo — doctor ko bhi ye batao 💾"
    ),
    "indian diet protein sources": (
        "Indian khane mein protein nahi hota — ye myth tod do.\n"
        "100g paneer = 18g protein. 1 cup dahi = 10g. 1 cup dal = 9g.\n"
        "Dal + rice = complete protein — amino acid profile complete hoti hai.\n"
        "Meat zaruri nahi — Indian vegetarian diet kafi hai gym ke liye 🥘\n"
        "Save karo aur apne gym bro ko share karo 💾"
    ),
    "gut health india": (
        "Gut = second brain. 95% serotonin gut mein banta hai — brain mein nahi.\n"
        "Poor gut health = poor mood + poor immunity + poor muscle recovery.\n"
        "Dahi, idli, kanji, pickle — ye Indian foods natural probiotics hain.\n"
        "Free gut health solution teri rasoi mein already hai 🦠\n"
        "Save karo — gut health pe dhyan do 💾"
    ),
    "cold water after workout myth": (
        "Workout ke baad cold water mat piyo — ye myth hai.\n"
        "Cold water core temperature regulate karta hai — harmful nahi hai.\n"
        "Room temperature slightly better — but cold water dangerous nahi.\n"
        "Jo pani available ho woh piyo — ye myth chhodo 🧊\n"
        "Save karo aur apne gym trainer ko bhi batao 💾"
    ),
    "processed food addiction": (
        "Processed food brain ke same reward receptors target karta hai jaise cocaine — MIT study.\n"
        "Ultra processed food = scientifically engineered addiction. Accident nahi hai ye.\n"
        "Simple rule: 5 se zyada ingredients listed hain? Processed hai.\n"
        "Label padho — ingredients list mein sab truth likhna hota hai 🍟\n"
        "Save karo — ye habit ek din mein badal sakti hai 💾"
    ),
    "yoga science benefits": (
        "Yoga sirf flexibility nahi — cortisol 20% reduce karta hai sirf 8 weeks mein.\n"
        "Harvard study: yoga anxiety medication jitna effective hai.\n"
        "10 min daily yoga = better sleep + lower stress + faster muscle recovery.\n"
        "Gym ke saath yoga add karo — results double honge 🧘\n"
        "Save karo — kal se start karo 💾"
    ),
}

DEFAULT_CAPTION = (
    "Daily fitness fact — backed by real science ✅\n"
    "Indian fitness education in Hinglish 🇮🇳\n"
    "Save karo aur share karo yaar 🏋️\n"
    "Follow @fitfacts.india for daily facts 💪"
)


async def send_video_to_telegram(video_path: Path, caption: str, hashtags: str):
    from telegram import Bot

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # Support both TELEGRAM_CHAT_ID and TELEGRAM_ALLOWED_USER_ID
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_ALLOWED_USER_ID", "")

    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID/TELEGRAM_ALLOWED_USER_ID not set")
        logger.error("TOKEN set: %s | CHAT_ID set: %s", bool(token), bool(chat_id))
        return False
    
    logger.info("Sending to chat_id: %s", chat_id)

    bot = Bot(token=token)

    logger.info("Sending video to Telegram: %s", video_path.name)

    async with bot:
        # Notification
        await bot.send_message(
            chat_id=chat_id,
            text=f"🎬 *New FitFacts Video Ready!*\n\n"
                 f"📁 `{video_path.name}`\n"
                 f"📊 Size: {video_path.stat().st_size // 1024}KB\n\n"
                 f"Sending video now...",
            parse_mode=None
        )

        # Send video
        with open(video_path, "rb") as vf:
            await bot.send_video(
                chat_id=chat_id,
                video=vf,
                caption=f"{caption}\n\n{hashtags}",
                supports_streaming=True,
            )

        # Send caption separately for easy copy-paste
        await bot.send_message(
            chat_id=chat_id,
            text=f"📋 *Caption — Copy for Instagram:*\n\n"
                 f"{caption}\n\n"
                 f"{hashtags}\n\n"
                 f"💡 _Tip: Put hashtags in first comment for cleaner caption_",
            parse_mode=None
        )

    logger.info("Video sent to Telegram ✅")
    return True


def get_topic_from_logs() -> str:
    """Read topic from latest pipeline log."""
    log_dir = Path("logs")
    if not log_dir.exists():
        return ""
    logs = sorted(log_dir.glob("pipeline_*.log"), reverse=True)
    if not logs:
        return ""
    try:
        content = logs[0].read_text()
        for line in content.split("\n"):
            if "Topic selected:" in line:
                return line.split("Topic selected:")[-1].strip().lower()
            if "Topic:" in line:
                return line.split("Topic:")[-1].strip().lower()
    except Exception:
        pass
    return ""


def get_caption_and_hashtags(topic: str) -> tuple[str, str]:
    caption = TOPIC_CAPTIONS.get(topic, DEFAULT_CAPTION)
    hashtags = TOPIC_HASHTAGS.get(topic, DEFAULT_HASHTAGS)
    logger.info("Topic: '%s' | Caption: %d chars | Hashtags: %s",
                topic, len(caption), hashtags)
    return caption, hashtags


async def main():
    videos_dir = Path("tmp/videos")
    if not videos_dir.exists():
        logger.error("No tmp/videos directory found")
        return

    # Exclude 13sec/short variant files — only the main video should ever
    # be picked here, even if the short-form render is re-enabled later.
    videos = sorted(
        (f for f in videos_dir.glob("*.mp4")
         if "13sec" not in f.stem and "short" not in f.stem),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not videos:
        logger.error("No videos found in tmp/videos/")
        return

    latest_video = videos[0]
    logger.info("Latest video: %s", latest_video)

    topic = get_topic_from_logs()
    caption, hashtags = get_caption_and_hashtags(topic)
    await send_video_to_telegram(latest_video, caption, hashtags)


if __name__ == "__main__":
    asyncio.run(main())
