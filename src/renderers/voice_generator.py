"""
Voice Generator - ElevenLabs TTS
Mood-based voice selection for gym/fitness Hinglish content.
"""

import logging
import subprocess
import uuid
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("tmp/audio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Free-tier friendly premade male voices for fitness content.
VOICES = {
    "energetic": "TX3LPaxmHKxFdv7VOQHJ",  # Liam - energetic social media creator
    "deep": "pNInz6obpgDQGcFmaJgB",       # Adam - dominant, firm
    "calm": "nPczCjzI2devNBz1zQrb",       # Brian - deep, resonant
    "hype": "IKne3meq5aSn9XLyUdCD",       # Charlie - deep, confident, energetic
}

TOPIC_MOOD_MAP = {
    "myth": "energetic",
    "myth bust": "energetic",
    "fact": "deep",
    "science": "calm",
    "workout": "hype",
    "exercise": "hype",
    "gym": "hype",
    "training": "hype",
    "sleep": "calm",
    "diet": "calm",
    "nutrition": "calm",
    "vitamin": "deep",
    "protein": "energetic",
    "fat": "deep",
    "weight": "energetic",
    "cardio": "hype",
    "running": "hype",
    "walking": "calm",
    "stress": "calm",
    "gut": "calm",
    "sugar": "energetic",
    "bmi": "deep",
}


def _pick_voice(topic: str) -> tuple[str, str]:
    """Returns (voice_id, mood) based on topic keywords."""
    topic_lower = topic.lower()
    for keyword, mood in TOPIC_MOOD_MAP.items():
        if keyword in topic_lower:
            return VOICES[mood], mood
    return VOICES["deep"], "deep"


class VoiceGenerator:
    def __init__(self, settings):
        self.settings = settings

    async def generate(self, text: str, topic: Literal["fitness"] | str = "") -> Path:
        """Generate voiceover. Uses configured voice first, then a free premade voice."""
        configured_voice_id = self.settings.elevenlabs_voice_id.strip()
        if configured_voice_id:
            voice_id, mood = configured_voice_id, "configured"
        else:
            voice_id, mood = _pick_voice(topic)
        logger.info("Voice selected: %s (mood=%s) for topic='%s'", voice_id, mood, topic)

        audio_id = uuid.uuid4().hex[:8]
        audio_path = OUTPUT_DIR / f"voice_{audio_id}.mp3"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": self.settings.elevenlabs_model_id,
                    "voice_settings": {
                        "stability": 0.4,
                        "similarity_boost": 0.8,
                        "style": 0.3,
                        "use_speaker_boost": True,
                    },
                },
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {401, 402, 403}:
                    logger.warning(
                        "ElevenLabs unavailable (%s). Falling back to local Windows TTS.",
                        exc.response.status_code,
                    )
                    return self._generate_windows_tts(text, audio_id)
                raise

        audio_path.write_bytes(resp.content)
        size_kb = audio_path.stat().st_size // 1024
        logger.info(
            "Audio saved: %s (%d KB) | voice=%s mood=%s",
            audio_path,
            size_kb,
            voice_id,
            mood,
        )
        return audio_path

    def _generate_windows_tts(self, text: str, audio_id: str) -> Path:
        """Generate a local WAV voiceover using Windows SAPI."""
        text_path = OUTPUT_DIR / f"voice_{audio_id}.txt"
        audio_path = OUTPUT_DIR / f"voice_{audio_id}.wav"
        text_path.write_text(text, encoding="utf-8")

        def ps_quote(value: Path) -> str:
            return "'" + str(value.resolve()).replace("'", "''") + "'"

        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$text = Get-Content -LiteralPath "
            f"{ps_quote(text_path)} -Raw; "
            "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$speaker.Rate = 1; "
            "$speaker.Volume = 100; "
            "$speaker.SetOutputToWaveFile("
            f"{ps_quote(audio_path)}"
            "); "
            "$speaker.Speak($text); "
            "$speaker.Dispose();"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Local Windows TTS failed:\n{result.stderr[-600:]}")

        size_kb = audio_path.stat().st_size // 1024
        logger.info("Local TTS audio saved: %s (%d KB)", audio_path, size_kb)
        return audio_path
