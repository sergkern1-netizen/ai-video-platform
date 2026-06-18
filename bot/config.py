import os


def get_bot_token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def get_allowed_user_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    return {int(part.strip()) for part in raw.split(",") if part.strip()}


def get_public_base_url() -> str:
    return os.environ["PUBLIC_BASE_URL"].rstrip("/")


def get_backend_url() -> str:
    return os.environ.get("BACKEND_URL", "http://localhost:8000")
