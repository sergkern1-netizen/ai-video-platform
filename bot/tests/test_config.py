from bot import config


def test_get_allowed_user_ids_parses_csv(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "111,222, 333")
    assert config.get_allowed_user_ids() == {111, 222, 333}


def test_get_allowed_user_ids_empty_when_unset(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    assert config.get_allowed_user_ids() == set()


def test_get_public_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.ngrok.io/")
    assert config.get_public_base_url() == "https://example.ngrok.io"


def test_get_bot_token_reads_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc123")
    assert config.get_bot_token() == "abc123"


def test_get_backend_url_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("BACKEND_URL", raising=False)
    assert config.get_backend_url() == "http://localhost:8000"
