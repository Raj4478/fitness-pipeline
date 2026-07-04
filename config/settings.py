"""
Settings — loads all config from environment variables.
Never hardcode keys. Use a .env file locally, Railway env vars in prod.
"""

from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM providers ─────────────────────────────────────────────────
    # Set to "gemini" or "groq" — both free. Avoid "deepseek" unless you add credits.
    llm_provider: Literal["deepseek", "gemini", "groq"] = "gemini"
    llm_max_retries: int = 3
    llm_timeout_seconds: int = 30

    # DeepSeek — requires paid credits. Leave blank if not using.
    deepseek_api_key: str = Field(default="", description="DeepSeek API key (optional)")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Gemini — free tier, 15 req/min. Recommended for starting out.
    # Valid model IDs: gemini-2.5-flash-lite, gemini-2.5-flash, gemini-2.0-flash
    gemini_api_key: str = Field(default="", description="Gemini API key")
    gemini_model: str = "gemini-2.5-flash-lite"

    # Groq — extremely cheap ($0.05/1M tokens), OpenAI-compatible, generous free tier.
    # Sign up free at: console.groq.com
    groq_api_key: str = Field(default="", description="Groq API key (optional)")
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.1-8b-instant"

    # ── ElevenLabs ────────────────────────────────────────────────────
    # Add up to 3 fallback keys — pipeline cycles through them when one runs out
    elevenlabs_api_key: str = Field(default="", description="ElevenLabs API key (primary)")
    elevenlabs_api_key_2: str = Field(default="", description="ElevenLabs API key (fallback 2)")
    elevenlabs_api_key_3: str = Field(default="", description="ElevenLabs API key (fallback 3)")
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"
    elevenlabs_model_id: str = "eleven_flash_v2_5"  # 2x free credits + better Hindi

    def elevenlabs_api_keys(self) -> list[str]:
        """Returns all configured ElevenLabs API keys in priority order.
        Keys are stripped of whitespace/newlines to prevent header errors."""
        return [
            k.strip() for k in [
                self.elevenlabs_api_key,
                self.elevenlabs_api_key_2,
                self.elevenlabs_api_key_3,
            ] if k.strip()
        ]

    # ── Creatomate ────────────────────────────────────────────────────
    creatomate_api_key: str = Field(default="", description="Creatomate API key")
    creatomate_template_id: str = Field(default="", description="Template UUID from Creatomate")
    creatomate_base_url: str = "https://api.creatomate.com/v1"

    # ── Buffer ────────────────────────────────────────────────────────
    buffer_access_token: str = Field(default="", description="Buffer access token")
    # NOTE: kept as a plain str, not list[str]. pydantic-settings treats
    # list[str] as a "complex" type and tries json.loads() on the raw env
    # string at the settings-source layer, BEFORE any field_validator runs
    # — so a comma-separated value like "id_1,id_2" (or an empty string
    # from an unset secret) would crash with a JSONDecodeError before our
    # own parsing ever got a chance to run. Splitting it ourselves via the
    # property below sidesteps that entirely.
    buffer_channels_raw: str = Field(
        default="",
        alias="BUFFER_CHANNELS",
        description="Comma-separated Buffer channel IDs",
    )

    # ── Pexels (stock video) ──────────────────────────────────────────
    pexels_api_key: str = Field(default="", description="Pexels API key")

    # ── GitHub Releases (video/audio storage) ────────────────────────
    # Token needs 'repo' scope. Create at github.com/settings/tokens
    gh_upload_token: str = Field(default="", description="GitHub token for release uploads")

    # ── App config ────────────────────────────────────────────────────
    db_path: Path = Path("data/runs.db")
    audio_tmp_dir: Path = Path("tmp/audio")
    log_level: str = "INFO"
    environment: Literal["development", "production"] = "development"

    @property
    def buffer_channels(self) -> list[str]:
        return [c.strip() for c in self.buffer_channels_raw.split(",") if c.strip()]

    @cached_property
    def is_production(self) -> bool:
        return self.environment == "production"

    def active_providers(self) -> list[str]:
        """Returns ordered list of LLM providers to try — primary first, then fallbacks."""
        all_keys = {
            "deepseek": self.deepseek_api_key,
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
        }
        result = [self.llm_provider]
        for name, key in all_keys.items():
            if name != self.llm_provider and key:
                result.append(name)
        return result

    def model_post_init(self, __context) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audio_tmp_dir.mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
