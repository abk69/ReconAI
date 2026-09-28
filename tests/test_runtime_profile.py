"""Single-operator profile checks. No secrets in assertion messages."""

import pytest
from pydantic import ValidationError

from app.core.config import ConfigurationError, Settings, enforce_profile

LOCAL_URL = "postgresql+psycopg://reconai:reconai@localhost:5432/reconai"
SAFE_URL = "postgresql+psycopg://reconai_app:not-the-local-default@db:5432/reconai"


def _settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_local_allows_debug_and_compose_credentials() -> None:
    settings = enforce_profile(
        _settings(app_env="local", debug=True, database_url=LOCAL_URL, gemini_api_key=None)
    )
    assert settings.app_env == "local"
    assert settings.debug is True
    assert settings.gemini_api_key is None


def test_demo_defaults_debug_off_without_explicit_flag() -> None:
    settings = enforce_profile(_settings(app_env="demo", database_url=SAFE_URL))
    assert settings.debug is False


def test_production_rejects_explicit_debug() -> None:
    with pytest.raises(ConfigurationError, match="cannot enable debug"):
        enforce_profile(_settings(app_env="production", debug=True, database_url=SAFE_URL))


def test_non_local_rejects_only_the_known_local_account() -> None:
    with pytest.raises(ConfigurationError, match="default local database credentials") as exc:
        enforce_profile(_settings(app_env="demo", debug=False, database_url=LOCAL_URL))
    message = str(exc.value)
    assert "reconai:reconai" not in message
    assert "@localhost" not in message

    short_password = enforce_profile(
        _settings(
            app_env="production",
            debug=False,
            database_url="postgresql+psycopg://app:short@db:5432/reconai",
        )
    )
    assert short_password.app_env == "production"


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="APP_ENV must be one of"):
        enforce_profile(_settings(app_env="staging", debug=False, database_url=SAFE_URL))


def test_settings_model_still_accepts_optional_gemini_key() -> None:
    settings = Settings(gemini_api_key=None)
    assert settings.gemini_api_key is None
    with pytest.raises(ValidationError):
        Settings(llm_max_retries=-1)
