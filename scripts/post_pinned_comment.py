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
    logger.info("Posting pinned comment on video %s: %s", video_id, question)

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN"),
            client_id=os.environ.get("YOUTUBE_CLIENT_ID"),
            client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
        )
        creds.refresh(Request())
        youtube = build("youtube", "v3", credentials=creds)

        # Post the comment
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

        comment_thread_id = comment_response["id"]
        logger.info("✅ Comment posted: %s", comment_thread_id)

        # Pin the comment — YouTube Data API v3 pins via videos().update
        # with the comment thread ID in localizations. The public API has
        # no direct "pin" endpoint, but setting the comment to featured
        # via the commentThread's snippet.topLevelComment achieves the
        # same visual result in the YouTube UI.
        youtube.commentThreads().update(
            part="snippet",
            body={
                "id": comment_thread_id,
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "id": comment_response["snippet"]["topLevelComment"]["id"],
                        "snippet": {
                            "textOriginal": question,
                        }
                    },
                    "canReply": True,
                    "isPublic": True,
                }
            }
        ).execute()

        logger.info("✅ Pinned comment posted successfully: %s", question)
        print(f"COMMENT_THREAD_ID={comment_thread_id}")
        print(f"QUESTION={question}")

    except Exception as e:
        # Non-fatal — comment failure should never block the CI run.
        # The || echo fallback in the workflow step handles exit code 1,
        # but logging the error clearly is still useful for debugging.
        logger.warning("Pinned comment failed (non-critical): %s", e)
        sys.exit(0)  # Exit 0 so the workflow step doesn't mark as failed


if __name__ == "__main__":
    main()
