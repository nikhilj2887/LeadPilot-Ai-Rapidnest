import pytest

from leadpilot.config import Settings


def test_settings_load_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "LEADPILOT_APP_NAME",
        "LEADPILOT_ENV",
        "LEADPILOT_LOG_LEVEL",
        "LEADPILOT_DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env(env_file=None)

    assert settings.app_name == "LeadPilot AI"
    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.database_url == "sqlite:///./data/leadpilot.db"


def test_settings_load_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEADPILOT_ENV", "test")
    monkeypatch.setenv("LEADPILOT_LOG_LEVEL", "debug")
    monkeypatch.setenv("LEADPILOT_DATABASE_URL", "sqlite:///:memory:")

    settings = Settings.from_env(env_file=None)

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.database_url == "sqlite:///:memory:"


def test_settings_reject_invalid_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEADPILOT_LOG_LEVEL", "verbose")

    with pytest.raises(ValueError, match="LEADPILOT_LOG_LEVEL"):
        Settings.from_env(env_file=None)
