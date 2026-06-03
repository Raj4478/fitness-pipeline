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

    async def generate(
        self, text: str, topic: Literal["fitness"] | str = ""
    ) -> tuple[Path, dict]:
        """
        Generate voiceover.
        Returns (audio_path, provider_info) where provider_info contains:
          - provider: "elevenlabs" or "gtts"
          - model: model name used
          - voice_id: voice ID used (ElevenLabs only)
          - key_index: which key was used (ElevenLabs only)
        """
        configured_voice_id = self.settings.elevenlabs_voice_id.strip()
        if configured_voice_id:
            voice_id, mood = configured_voice_id, "configured"
        else:
            voice_id, mood = _pick_voice(topic)
        logger.info("Voice selected: %s (mood=%s) for topic='%s'", voice_id, mood, topic)

        audio_id = uuid.uuid4().hex[:8]
        audio_path = OUTPUT_DIR / f"voice_{audio_id}.mp3"

        api_keys = self.settings.elevenlabs_api_keys()
        if not api_keys:
            logger.warning("No ElevenLabs API keys configured. Using gTTS fallback.")
            path = self._generate_fallback_tts(text, audio_id)
            return path, {"provider": "gtts", "model": "Google TTS (hi)", "voice_id": None, "key_index": None}

        last_error = None
        for idx, api_key in enumerate(api_keys, start=1):
            try:
                logger.info("Trying ElevenLabs key %d/%d", idx, len(api_keys))
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                        headers={
                            "xi-api-key": api_key.strip(),
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
                    resp.raise_for_status()

                audio_path.write_bytes(resp.content)
                size_kb = audio_path.stat().st_size // 1024
                provider_info = {
                    "provider": "elevenlabs",
                    "model": self.settings.elevenlabs_model_id,
                    "voice_id": voice_id,
                    "key_index": idx,
                }
                logger.info(
                    "Audio saved: %s (%d KB) | key=%d voice=%s model=%s mood=%s",
                    audio_path, size_kb, idx, voice_id,
                    self.settings.elevenlabs_model_id, mood,
                )
                return audio_path, provider_info

            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code in {401, 402, 403}:
                    logger.warning(
                        "ElevenLabs key %d/%d exhausted (HTTP %d) — trying next key",
                        idx, len(api_keys), code,
                    )
                    last_error = exc
                    continue
                raise

        # All keys exhausted — fall back to gTTS
        logger.warning(
            "All %d ElevenLabs keys exhausted. Using gTTS fallback.",
            len(api_keys),
        )
        path = self._generate_fallback_tts(text, audio_id)
        return path, {"provider": "gtts", "model": "Google TTS (hi)", "voice_id": None, "key_index": None}

    def _generate_fallback_tts(self, text: str, audio_id: str) -> Path:
        """
        Cross-platform TTS fallback.
        Windows: PowerShell SAPI
        Linux (GitHub Actions): gTTS (Google TTS, free)
        """
        import platform
        system = platform.system()
        logger.info("Using fallback TTS on %s", system)

        if system == "Windows":
            return self._windows_tts(text, audio_id)
        else:
            return self._gtts_fallback(text, audio_id)

    def _windows_tts(self, text: str, audio_id: str) -> Path:
        """Windows PowerShell SAPI TTS."""
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
            "$speaker.Rate = 1; $speaker.Volume = 100; "
            f"$speaker.SetOutputToWaveFile({ps_quote(audio_path)}); "
            "$speaker.Speak($text); $speaker.Dispose();"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Windows TTS failed:\n{result.stderr[-400:]}")
        logger.info("Windows TTS saved: %s", audio_path)
        return audio_path

    def _gtts_fallback(self, text: str, audio_id: str) -> Path:
        """
        Google TTS fallback for Linux/GitHub Actions.
        Free, no API key, supports Hindi.
        """
        try:
            from gtts import gTTS
        except ImportError as exc:
            raise RuntimeError("gTTS is not installed. Install it with `pip install gTTS`.") from exc

        audio_path = OUTPUT_DIR / f"voice_{audio_id}.mp3"
        logger.info("Using gTTS fallback (Hindi)...")

        # gTTS with Hindi language
        tts = gTTS(text=text, lang="hi", slow=False)
        tts.save(str(audio_path))

        size_kb = audio_path.stat().st_size // 1024
        logger.info("gTTS audio saved: %s (%d KB)", audio_path, size_kb)
        return audio_path

    # Keep old name as alias for compatibility
    def _generate_windows_tts(self, text: str, audio_id: str) -> Path:
        return self._generate_fallback_tts(text, audio_id)
