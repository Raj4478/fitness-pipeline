"""
Auto Pinned Comment — posts an engagement question on YouTube video.
Runs after upload. Pins the comment automatically.
"""

import os
import sys
import logging
import random

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Engagement questions per topic keyword
QUESTIONS = {
    "protein":     ["Aap roz kitna protein lete ho? Comment mein batao! 💪", "Kya aapko pata tha protein ki ye limit? 🤔"],
    "vitamin":     ["Kya aapne kabhi Vitamin D test karaya hai? 🌞", "Aap dhoop mein kitna time bitatay ho daily?"],
    "sleep":       ["Aap roz kitne ghante sote ho? Honestly batao! 😴", "Sleep priority dete ho ya sacrifice karte ho gym ke liye?"],
    "gym":         ["Gym mein ye galti karte the? 🏋️ Comment below!", "Kitne saal se gym ja rahe ho? Batao!"],
    "creatine":    ["Creatine use karte ho? Ya dar lagta hai? 😅", "Creatine ke baare mein kya sochte ho?"],
    "fat":         ["Belly fat se pareshan ho? Kya try kiya ab tak?", "Fat loss ke liye kya karte ho? Batao!"],
    "sugar":       ["Sugar-free drinks peete ho? Sach batao! 🥤", "Aap daily kitna sugar consume karte ho?"],
    "walking":     ["Roz walk karte ho? Kitne steps daily? 🚶", "Walk ya run — aap kya prefer karte ho?"],
    "bmi":         ["Aapka BMI kya hai? Comment karo! 📊", "BMI ne kabhi galat bola aapko? Share karo!"],
    "default":     ["Ye fact useful laga? Save karo aur share karo! 💪",
                    "Kaunsa fitness myth aapko sabse zyada surprise karta hai? 🤔",
                    "Aapka fitness goal kya hai 2026 mein? Comment karo! 🏋️",
                    "Ye jaankar acha laga? Apne gym buddy ko tag karo! 🔥",
                    "Agree ho ya nahi? Comment mein batao! 👇"]
}


def get_question(topic: str) -> str:
    topic_lower = topic.lower()
    for key, questions in QUESTIONS.items():
        if key in topic_lower:
            return random.choice(questions)
    return random.choice(QUESTIONS["default"])


def main():
    video_id = os.environ.get("YOUTUBE_VIDEO_ID", "")
    topic = os.environ.get("VIDEO_TOPIC", "fitness")

    if not video_id:
        logger.error("YOUTUBE_VIDEO_ID not set")
        sys.exit(1)

    question = get_question(topic)
    logger.info("Posting pinned comment: %s", question)

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN"),
            client_id=os.environ.get("YOUTUBE_CLIENT_ID"),
            client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
        )
        youtube = build("youtube", "v3", credentials=creds)

        # Post comment
        comment_response = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": question
                        }
                    }
                }
            }
        ).execute()

        comment_id = comment_response["id"]
        logger.info("Comment posted: %s", comment_id)

        # Pin the comment
        youtube.comments().setModerationStatus(
            id=comment_id,
            moderationStatus="published",
        ).execute()

        # Mark as pinned via video update
        youtube.comments().update(
            part="snippet",
            body={
                "id": comment_id,
                "snippet": {
                    "textOriginal": question,
                    "videoId": video_id,
                }
            }
        ).execute()

        logger.info("✅ Pinned comment posted: %s", question)
        print(f"COMMENT_ID={comment_id}")
        print(f"QUESTION={question}")

    except Exception as e:
        logger.error("Pinned comment failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
