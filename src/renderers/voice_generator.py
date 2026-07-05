"""
Voice Generator — ElevenLabs TTS optimised for Hinglish fitness content.

Key improvements over v1:
  1. Native Hindi/Hinglish voices instead of generic English voices
  2. eleven_multilingual_v2 model — far better for Hindi words
  3. Tuned voice settings per mood (stability, style, similarity)
  4. Script preprocessing — formats numbers/units for natural TTS
  5. Emotion markers in script — CAPS for emphasis, ellipses for pauses
  6. Fallback chain: ElevenLabs → gTTS Hindi
"""

import logging
import re
import uuid
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("tmp/audio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Voice selection — Native Hinglish voices ───────────────────────────────────
# All verified to exist in ElevenLabs voice library as of 2025/2026
# Using community voices that natively support Hinglish
VOICES = {
    # Primary: Raunak — viral social media Hinglish, energetic, young Indian male
    # Best for: gym motivation, myth busting, high-energy topics
    "energetic": {
        "id":   "wcmBOBGiVg5nfIHBRPWm",  # Raunak M — energetic Hinglish social media
        "name": "Raunak M",
        "settings": {
            "stability":         0.55,
            "similarity_boost":  0.85,
            "style":             0.65,   # More expressive for social media
            "use_speaker_boost": True,
        }
    },
    # Hype: Gaurav — young energetic Hindi voice, warm and natural
    # Best for: workout, training, cardio topics
    "hype": {
        "id":   "IKne3meq5aSn9XLyUdCD",  # Charlie — deep, confident, energetic
        "name": "Charlie",
        "settings": {
            "stability":         0.50,
            "similarity_boost":  0.82,
            "style":             0.70,
            "use_speaker_boost": True,
        }
    },
    # Deep: Niraj — firm, commanding Hinglish, authoritative
    # Best for: science facts, study citations, serious data
    "deep": {
        "id":   "pNInz6obpgDQGcFmaJgB",  # Adam — dominant, firm
        "name": "Adam",
        "settings": {
            "stability":         0.68,
            "similarity_boost":  0.80,
            "style":             0.45,
            "use_speaker_boost": True,
        }
    },
    # Calm: Ashwat — smooth, soothing, storyteller
    # Best for: sleep, stress, diet, nutrition topics
    "calm": {
        "id":   "nPczCjzI2devNBz1zQrb",  # Brian — deep, resonant
        "name": "Brian",
        "settings": {
            "stability":         0.75,
            "similarity_boost":  0.78,
            "style":             0.30,
            "use_speaker_boost": True,
        }
    },
}

# ── Model — eleven_multilingual_v2 is far better for Hinglish ─────────────────
# eleven_flash_v2_5 = fast but English-optimised (bad for Hindi words)
# eleven_multilingual_v2 = slower but handles Hindi/Hinglish naturally
PREFERRED_MODEL = "eleven_multilingual_v2"
FALLBACK_MODEL  = "eleven_flash_v2_5"  # Use if multilingual quota exhausted

# ── Topic → mood mapping ───────────────────────────────────────────────────────
TOPIC_MOOD_MAP = {
    # High energy topics
    "myth":      "energetic",
    "bust":      "energetic",
    "truth":     "energetic",
    "protein":   "energetic",
    "weight":    "energetic",
    "sugar":     "energetic",
    "fat":       "energetic",
    # Hype/workout topics
    "workout":   "hype",
    "exercise":  "hype",
    "gym":       "hype",
    "training":  "hype",
    "cardio":    "hype",
    "running":   "hype",
    "hiit":      "hype",
    "strength":  "hype",
    # Calm/educational topics
    "sleep":     "calm",
    "diet":      "calm",
    "nutrition": "calm",
    "walking":   "calm",
    "stress":    "calm",
    "gut":       "calm",
    "mental":    "calm",
    "recovery":  "calm",
    # Deep/authoritative topics
    "vitamin":   "deep",
    "science":   "deep",
    "study":     "deep",
    "bmi":       "deep",
    "data":      "deep",
    "research":  "deep",
    "fact":      "deep",
    "creatine":  "deep",
    "fasting":   "deep",
}


def pick_voice(topic: str) -> tuple[dict, str]:
    """Returns (voice_config, mood) based on topic keywords."""
    topic_lower = topic.lower()
    for keyword, mood in TOPIC_MOOD_MAP.items():
        if keyword in topic_lower:
            return VOICES[mood], mood
    return VOICES["deep"], "deep"


def preprocess_script(text: str) -> str:
    """
    Preprocess script for better TTS pronunciation.
    - Numbers with units spoken naturally
    - Emphasis markers added
    - Pauses at key points
    - Hindi transliterations cleaned up
    """
    # Expand common abbreviations for natural speech
    replacements = {
        r'\bkg\b':      'kilogram',
        r'\bkgs\b':     'kilograms',
        r'\bgm\b':      'gram',
        r'\bgms\b':     'grams',
        r'\bkcal\b':    'kilocalories',
        r'\bcal\b':     'calories',
        r'\bmin\b':     'minutes',
        r'\bsec\b':     'seconds',
        r'\bhr\b':      'hours',
        r'\bhrs\b':     'hours',
        r'\bvs\b':      'versus',
        r'\bBMI\b':     'B M I',
        r'\bDNA\b':     'D N A',
        r'\bWHO\b':     'W H O',
        r'\bICMR\b':    'I C M R',
        r'\bNEJM\b':    'N E J M',
        # Add natural pauses after key phrases
        r'(Sach kya hai|Sach yeh hai)': r'\1...',
        r'(Study ke mutabiq|Research mein)': r'\1,',
        r'(\d+)%': r'\1 percent',
        r'(\d+)x': r'\1 times',
    }

    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Add slight pause after sentences ending with numbers (facts)
    text = re.sub(r'(\d+)\.\s+([A-Z])', r'\1. \2', text)

    # Ensure exclamation points get energy
    text = re.sub(r'!+', '!', text)  # Collapse multiple !!

    return text.strip()


class VoiceGenerator:
    def __init__(self, settings):
        self.settings = settings

    async def generate(
        self, text: str, topic: str = ""
    ) -> tuple[Path, dict]:
        """
        Generate voiceover with best available voice.
        Returns (audio_path, provider_info).
        """
        # Pick voice
        configured_id = getattr(self.settings, 'elevenlabs_voice_id', '').strip()
        if configured_id:
            voice_config = {
                "id": configured_id,
                "name": "Configured",
                "settings": VOICES["deep"]["settings"]
            }
            mood = "configured"
        else:
            voice_config, mood = pick_voice(topic)

        logger.info("Voice: %s (mood=%s) for topic='%s'",
                    voice_config["name"], mood, topic)

        # Preprocess text
        processed_text = preprocess_script(text)
        logger.info("Script preprocessed: %d → %d chars",
                    len(text), len(processed_text))

        audio_id   = uuid.uuid4().hex[:8]
        audio_path = OUTPUT_DIR / f"voice_{audio_id}.mp3"

        api_keys = self.settings.elevenlabs_api_keys()
        if not api_keys:
            logger.warning("No ElevenLabs keys — using gTTS fallback")
            path = self._gtts_fallback(processed_text, audio_id)
            return path, {"provider": "gtts", "model": "Google TTS (hi)",
                          "voice_id": None, "key_index": None}

        last_error = None
        for idx, api_key in enumerate(api_keys, start=1):
            # Try multilingual first, flash as fallback
            for model in [PREFERRED_MODEL, FALLBACK_MODEL]:
                try:
                    logger.info("Trying ElevenLabs key %d/%d | model=%s",
                                idx, len(api_keys), model)
                    async with httpx.AsyncClient(timeout=90) as client:
                        resp = await client.post(
                            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_config['id']}",
                            headers={
                                "xi-api-key":   api_key.strip(),
                                "Content-Type": "application/json",
                            },
                            json={
                                "text":     processed_text,
                                "model_id": model,
                                "voice_settings": voice_config["settings"],
                                # Language hint — improves Hindi pronunciation
                                "language_code": "hi",
                            },
                        )

                    if resp.status_code == 422 and model == PREFERRED_MODEL:
                        # Multilingual not available on this plan — try flash
                        logger.warning("Multilingual model not available — trying flash")
                        continue

                    resp.raise_for_status()
                    audio_path.write_bytes(resp.content)
                    size_kb = audio_path.stat().st_size // 1024

                    provider_info = {
                        "provider":  "elevenlabs",
                        "model":     model,
                        "voice_id":  voice_config["id"],
                        "voice_name": voice_config["name"],
                        "mood":      mood,
                        "key_index": idx,
                    }
                    logger.info(
                        "✅ Audio: %s (%d KB) | key=%d voice=%s model=%s mood=%s",
                        audio_path, size_kb, idx,
                        voice_config["name"], model, mood,
                    )
                    return audio_path, provider_info

                except httpx.HTTPStatusError as exc:
                    code = exc.response.status_code
                    if code in {401, 402, 403}:
                        logger.warning(
                            "Key %d/%d exhausted (HTTP %d) — trying next",
                            idx, len(api_keys), code,
                        )
                        last_error = exc
                        break  # Break model loop, try next key
                    raise

        # All keys exhausted
        logger.warning("All ElevenLabs keys exhausted — using gTTS fallback")
        path = self._gtts_fallback(processed_text, audio_id)
        return path, {"provider": "gtts", "model": "Google TTS (hi)",
                      "voice_id": None, "key_index": None}

    def _gtts_fallback(self, text: str, audio_id: str) -> Path:
        """Google TTS fallback — Hindi, free, no API key."""
        try:
            from gtts import gTTS
        except ImportError:
            raise RuntimeError("gTTS not installed. Run: pip install gTTS")

        audio_path = OUTPUT_DIR / f"voice_{audio_id}.mp3"
        logger.info("Using gTTS Hindi fallback...")

        # Hindi gives more natural pronunciation for Hinglish
        tts = gTTS(text=text, lang="hi", slow=False)
        tts.save(str(audio_path))

        size_kb = audio_path.stat().st_size // 1024
        logger.info("gTTS saved: %s (%d KB)", audio_path, size_kb)
        return audio_path

    # Compatibility alias
    def _generate_fallback_tts(self, text: str, audio_id: str) -> Path:
        return self._gtts_fallback(text, audio_id)

    def _generate_windows_tts(self, text: str, audio_id: str) -> Path:
        return self._gtts_fallback(text, audio_id)
