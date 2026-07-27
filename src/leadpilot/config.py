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

        return cls(
            app_name=os.getenv("LEADPILOT_APP_NAME", "LeadPilot AI").strip(),
            environment=os.getenv("LEADPILOT_ENV", "development").strip(),
            log_level=log_level,
            database_url=database_url,
        )

    @property
    def numeric_log_level(self) -> int:
        return getattr(logging, self.log_level)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
