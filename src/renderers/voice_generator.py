"""
Voice Generator — ElevenLabs TTS
Mood-based voice selection for gym/fitness Hinglish content.
"""

import logging
import uuid
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("tmp/audio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Voice pool — gym/fitness channel ──────────────────────────────────────────
# czQ9pLzjRaF61EAYjcPC — Ranbir  (deep, authoritative)
# IMzcdjL6UK1gZxag6QAU — Viraj   (energetic, youthful)
# ypnkIsDASPgHZuanrF0q — Parveen (calm, informative)
# SGbOfpm28edC83pZ9iGb — 4th voice (hype/intense)

VOICES = {
    "energetic": "IMzcdjL6UK1gZxag6QAU",   # Viraj — youthful energy, myth busting
    "deep":      "czQ9pLzjRaF61EAYjcPC",   # Ranbir — authoritative, facts
    "calm":      "ypnkIsDASPgHZuanrF0q",   # Parveen — science explanation
    "hype":      "SGbOfpm28edC83pZ9iGb",   # 4th — intense, workout content
}

# Topic keyword → mood mapping
TOPIC_MOOD_MAP = {
    "myth":        "energetic",
    "myth bust":   "energetic",
    "fact":        "deep",
    "science":     "calm",
    "workout":     "hype",
    "exercise":    "hype",
    "gym":         "hype",
    "training":    "hype",
    "sleep":       "calm",
    "diet":        "calm",
    "nutrition":   "calm",
    "vitamin":     "deep",
    "protein":     "energetic",
    "fat":         "deep",
    "weight":      "energetic",
    "cardio":      "hype",
    "running":     "hype",
    "walking":     "calm",
    "stress":      "calm",
    "gut":         "calm",
    "sugar":       "energetic",
    "bmi":         "deep",
}

def _pick_voice(topic: str) -> tuple[str, str]:
    """Returns (voice_id, mood) based on topic keywords."""
    topic_lower = topic.lower()
    for keyword, mood in TOPIC_MOOD_MAP.items():
        if keyword in topic_lower:
            return VOICES[mood], mood
    # Default — deep/authoritative for unknown topics
    return VOICES["deep"], "deep"


class VoiceGenerator:
    def __init__(self, settings):
        self.settings = settings

    async def generate(self, text: str, topic: str = "") -> Path:
        """Generate voiceover. Picks voice based on topic mood."""
        voice_id, mood = _pick_voice(topic)
        logger.info("Voice selected: %s (mood=%s) for topic='%s'", voice_id, mood, topic)

        audio_path = OUTPUT_DIR / f"voice_{uuid.uuid4().hex[:8]}.mp3"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.4,
                        "similarity_boost": 0.8,
                        "style": 0.3,
                        "use_speaker_boost": True,
                    },
                },
            )
            resp.raise_for_status()

        audio_path.write_bytes(resp.content)
        size_kb = audio_path.stat().st_size // 1024
        logger.info("Audio saved: %s (%d KB) | voice=%s mood=%s", audio_path, size_kb, voice_id, mood)
        return audio_path
