from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    environment: str
    log_level: str
    database_url: str
    discovery_connect_timeout: float = 5.0
    discovery_read_timeout: float = 10.0
    discovery_max_pages: int = 9
    discovery_max_response_bytes: int = 2_000_000
    discovery_user_agent: str = "LeadPilot/0.1 Website Discovery"
    discovery_retry_count: int = 1
    discovery_slow_response_ms: int = 3000
    ai_enabled: bool = False
    ai_provider: str = "openai"
    ai_model: str = "gpt-5-mini"
    ai_api_key: str | None = None
    ai_timeout_seconds: float = 60.0
    ai_max_retries: int = 1
    ai_temperature: float = 0.2
    ai_max_output_tokens: int = 6000
    ai_input_price_per_million: float | None = None
    ai_output_price_per_million: float | None = None

    @classmethod
    def from_env(cls, env_file: str | None = ".env") -> Settings:
        if env_file:
            load_dotenv(env_file, override=False)

        log_level = os.getenv("LEADPILOT_LOG_LEVEL", "INFO").upper()
        if log_level not in VALID_LOG_LEVELS:
            valid = ", ".join(sorted(VALID_LOG_LEVELS))
            raise ValueError(f"LEADPILOT_LOG_LEVEL must be one of: {valid}")

        database_url = os.getenv(
            "LEADPILOT_DATABASE_URL", "sqlite:///./data/leadpilot.db"
        ).strip()
        if not database_url:
            raise ValueError("LEADPILOT_DATABASE_URL must not be empty")

        api_key = os.getenv("LEADPILOT_AI_API_KEY", "").strip() or None
        requested_ai = os.getenv("LEADPILOT_AI_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return cls(
            app_name=os.getenv("LEADPILOT_APP_NAME", "LeadPilot AI").strip(),
            environment=os.getenv("LEADPILOT_ENV", "development").strip(),
            log_level=log_level,
            database_url=database_url,
            discovery_connect_timeout=float(
                os.getenv("LEADPILOT_DISCOVERY_CONNECT_TIMEOUT", "5")
            ),
            discovery_read_timeout=float(
                os.getenv("LEADPILOT_DISCOVERY_READ_TIMEOUT", "10")
            ),
            discovery_max_pages=int(os.getenv("LEADPILOT_DISCOVERY_MAX_PAGES", "9")),
            discovery_max_response_bytes=int(
                os.getenv("LEADPILOT_DISCOVERY_MAX_RESPONSE_BYTES", "2000000")
            ),
            discovery_user_agent=os.getenv(
                "LEADPILOT_DISCOVERY_USER_AGENT",
                "LeadPilot/0.1 Website Discovery",
            ).strip(),
            discovery_retry_count=int(
                os.getenv("LEADPILOT_DISCOVERY_RETRY_COUNT", "1")
            ),
            discovery_slow_response_ms=int(
                os.getenv("LEADPILOT_DISCOVERY_SLOW_RESPONSE_MS", "3000")
            ),
            ai_enabled=requested_ai and bool(api_key),
            ai_provider=os.getenv("LEADPILOT_AI_PROVIDER", "openai").strip().lower(),
            ai_model=os.getenv("LEADPILOT_AI_MODEL", "gpt-5-mini").strip(),
            ai_api_key=api_key,
            ai_timeout_seconds=float(os.getenv("LEADPILOT_AI_TIMEOUT_SECONDS", "60")),
            ai_max_retries=int(os.getenv("LEADPILOT_AI_MAX_RETRIES", "1")),
            ai_temperature=float(os.getenv("LEADPILOT_AI_TEMPERATURE", "0.2")),
            ai_max_output_tokens=int(
                os.getenv("LEADPILOT_AI_MAX_OUTPUT_TOKENS", "6000")
            ),
            ai_input_price_per_million=_optional_float(
                "LEADPILOT_AI_INPUT_PRICE_PER_MILLION"
            ),
            ai_output_price_per_million=_optional_float(
                "LEADPILOT_AI_OUTPUT_PRICE_PER_MILLION"
            ),
        )

    @property
    def numeric_log_level(self) -> int:
        return getattr(logging, self.log_level)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def _optional_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None
