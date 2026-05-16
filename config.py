"""
OpenAlpha - Quant — Application Configuration
All settings loaded from environment / .env file.
"""
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM provider: "anthropic" or "openai"
    LLM_PROVIDER: str = "anthropic"

    # Model identifier — claude-sonnet-4-20250514 for Anthropic, gpt-4o for OpenAI
    LLM_MODEL: str = "claude-sonnet-4-20250514"

    # API key — required at runtime; Optional here so startup doesn't fail before
    # the user has created their .env file. Validated inside llm_client.generate().
    LLM_API_KEY: Optional[str] = None

    # Sampling temperature (0.7–1.0 keeps alpha variety without losing coherence)
    LLM_TEMPERATURE: float = 0.8

    # Max tokens per completion — 2000 is enough for the 7-field format
    LLM_MAX_TOKENS: int = 2000

    # Hard cap on generation cycles per session
    MAX_CYCLES: int = 20

    # Max mutation attempts before forcing a full ideation restart
    MAX_MUTATIONS: int = 4

    # Filesystem path for session JSON persistence
    SESSION_DIR: Path = Path("./sessions")

    # Python logging level
    LOG_LEVEL: str = "INFO"

    # ── WorldQuant BRAIN API credentials ────────────────────────────────────
    # Set these to enable automatic alpha submission after local validation.
    # Get them from your worldquantbrain.com login (same email/password).
    BRAIN_EMAIL: Optional[str] = None
    BRAIN_PASSWORD: Optional[str] = None

    # Set to True to automatically submit passing alphas to BRAIN for simulation.
    # Requires BRAIN_EMAIL and BRAIN_PASSWORD to be set.
    BRAIN_SUBMIT_ENABLED: bool = False

    # Max seconds to wait for BRAIN simulation to complete (simulations ~60-180s)
    BRAIN_POLL_TIMEOUT: int = 300

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }



# Module-level singleton — import this everywhere
settings = Settings()
