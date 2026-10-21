import pytest
from pydantic import ValidationError

from notsolazy.config import Settings


def test_offline_settings_need_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(_env_file=None, sec_user_agent="")
    assert not settings.summaries_enabled
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        settings.require_sec_identity()


def test_sec_identity_and_rate_limit() -> None:
    settings = Settings(_env_file=None, sec_user_agent="NotSoLazy/0.1 contact@example.org")
    assert settings.require_sec_identity().endswith("contact@example.org")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, sec_requests_per_second=10)


def test_secrets_are_redacted() -> None:
    settings = Settings(_env_file=None, anthropic_api_key="private-key")
    assert "private-key" not in repr(settings)
    assert settings.summaries_enabled
