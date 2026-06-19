# Telegram Bot Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Telegram bot (`ai-video-platform/bot/`) that lets an allowlisted set of Telegram users generate videos through chat, by calling the existing FastAPI backend over HTTP — no backend changes required.

**Architecture:** Separate Python process using aiogram 3.x with long polling. An FSM-driven `/generate` flow collects topic + format, posts to `POST /videos/`, then a background asyncio task polls `GET /videos/{id}/status` every 5s and pushes a message when done. A local `bot_state.db` SQLite file (separate from the backend's `db.sqlite3`) records which user requested which video, powering `/history`. Download links use `PUBLIC_BASE_URL` (a tunnel address) instead of `localhost` so they work from a phone.

**Tech Stack:** Python, aiogram 3.x, httpx (async), SQLite (stdlib `sqlite3`), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-18-telegram-bot-design.md`

---

### Task 1: Project scaffolding

**Files:**
- Create: `ai-video-platform/bot/__init__.py`
- Create: `ai-video-platform/bot/requirements.txt`
- Modify: `ai-video-platform/.env.example`
- Modify: `ai-video-platform/.gitignore`
- Create: `ai-video-platform/pytest.ini`
- Create: `ai-video-platform/bot/tests/__init__.py`

- [ ] **Step 1: Create the `bot` package directory and empty `__init__.py`**

```bash
mkdir -p "ai-video-platform/bot/tests"
touch "ai-video-platform/bot/__init__.py"
touch "ai-video-platform/bot/tests/__init__.py"
```

- [ ] **Step 2: Write `bot/requirements.txt`**

```
aiogram==3.7.0
httpx==0.27.0
python-dotenv==1.0.1
pytest==8.2.2
pytest-asyncio==0.23.7
```

- [ ] **Step 3: Add new variables to `.env.example`**

Append to the existing file (current content: `OPENAI_API_KEY`, `PEXELS_API_KEY`, `DB_PATH`, `REDIS_URL`):

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=123456,789012
PUBLIC_BASE_URL=https://your-tunnel-subdomain.example.com
BACKEND_URL=http://localhost:8000
```

- [ ] **Step 4: Add `bot_state.db` to `.gitignore`**

Current `.gitignore` content:
```
output/*.mp4
temp/
.env
__pycache__/
.pytest_cache/
db.sqlite3
logs/
```

Append one line: `bot_state.db`

- [ ] **Step 5: Create `pytest.ini` at the `ai-video-platform/` root**

```ini
[pytest]
asyncio_mode = auto
```

This lets `async def test_...` functions in `bot/tests/` run without per-test `@pytest.mark.asyncio` decorators. It has no effect on the existing synchronous tests in `backend/tests/`.

- [ ] **Step 6: Install dependencies**

Run: `pip install -r ai-video-platform/bot/requirements.txt`
Expected: aiogram, httpx, pytest-asyncio install without errors (httpx/pytest already satisfied from backend's requirements).

- [ ] **Step 7: Commit**

```bash
cd ai-video-platform
git add bot/__init__.py bot/tests/__init__.py bot/requirements.txt .env.example .gitignore pytest.ini
git commit -m "chore: scaffold telegram bot package"
```

---

### Task 2: Config loader (`bot/config.py`)

**Files:**
- Create: `ai-video-platform/bot/config.py`
- Test: `ai-video-platform/bot/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# ai-video-platform/bot/tests/test_config.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `ai-video-platform/`): `python -m pytest bot/tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.config'` (or `ImportError`)

- [ ] **Step 3: Write `bot/config.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest bot/tests/test_config.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd ai-video-platform
git add bot/config.py bot/tests/test_config.py
git commit -m "feat: telegram bot config loader"
```

---

### Task 3: Local request history store (`bot/state.py`)

**Files:**
- Create: `ai-video-platform/bot/state.py`
- Test: `ai-video-platform/bot/tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

```python
# ai-video-platform/bot/tests/test_state.py
import pytest

from bot import state


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test_bot.db")
    monkeypatch.setenv("BOT_DB_PATH", db_file)
    state.init_db()
    yield


def test_add_request_and_get_history():
    state.add_request("vid-1", 111, "AI trends", "short")
    history = state.get_history(111)
    assert len(history) == 1
    assert history[0]["video_id"] == "vid-1"
    assert history[0]["topic"] == "AI trends"
    assert history[0]["format"] == "short"


def test_get_history_filters_by_user():
    state.add_request("vid-1", 111, "Topic A", "short")
    state.add_request("vid-2", 222, "Topic B", "long")
    history = state.get_history(111)
    assert len(history) == 1
    assert history[0]["video_id"] == "vid-1"


def test_get_history_respects_limit():
    for i in range(7):
        state.add_request(f"vid-{i}", 111, f"Topic {i}", "short")
    history = state.get_history(111, limit=5)
    assert len(history) == 5


def test_get_history_empty_for_unknown_user():
    assert state.get_history(999) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest bot/tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.state'`

- [ ] **Step 3: Write `bot/state.py`**

```python
import sqlite3
import os
from contextlib import contextmanager


def _db_path() -> str:
    return os.environ.get("BOT_DB_PATH", "bot_state.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                video_id    TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                topic       TEXT NOT NULL,
                format      TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


def add_request(video_id: str, user_id: int, topic: str, format: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO requests (video_id, user_id, topic, format) VALUES (?, ?, ?, ?)",
            (video_id, user_id, topic, format),
        )


def get_history(user_id: int, limit: int = 5) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM requests WHERE user_id = ? ORDER BY created_at DESC, video_id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest bot/tests/test_state.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd ai-video-platform
git add bot/state.py bot/tests/test_state.py
git commit -m "feat: telegram bot request history store"
```

---

### Task 4: Backend HTTP client (`bot/client.py`)

**Files:**
- Create: `ai-video-platform/bot/client.py`
- Test: `ai-video-platform/bot/tests/test_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# ai-video-platform/bot/tests/test_client.py
from unittest.mock import patch, AsyncMock, MagicMock

from bot import client


def _mock_async_client(response: MagicMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.post.return_value = response
    mock_client.get.return_value = response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


async def test_create_video_returns_parsed_json():
    response = MagicMock()
    response.json.return_value = {"id": "abc"}
    response.raise_for_status.return_value = None
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        result = await client.create_video("AI news", "short")

    assert result == {"id": "abc"}
    mock_client.post.assert_called_once_with(
        "/videos/", json={"topic": "AI news", "format": "short"}
    )


async def test_get_status_returns_parsed_json():
    response = MagicMock()
    response.json.return_value = {"status": "completed"}
    response.raise_for_status.return_value = None
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_status("vid-1")

    assert result == {"status": "completed"}
    mock_client.get.assert_called_once_with("/videos/vid-1/status")


async def test_create_video_raises_on_http_error():
    response = MagicMock()
    response.raise_for_status.side_effect = Exception("boom")
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        try:
            await client.create_video("AI news", "short")
            assert False, "expected an exception"
        except Exception as exc:
            assert str(exc) == "boom"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest bot/tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.client'`

- [ ] **Step 3: Write `bot/client.py`**

```python
import httpx

from bot.config import get_backend_url


async def create_video(topic: str, format: str) -> dict:
    async with httpx.AsyncClient(base_url=get_backend_url(), timeout=10) as session:
        response = await session.post("/videos/", json={"topic": topic, "format": format})
        response.raise_for_status()
        return response.json()


async def get_status(video_id: str) -> dict:
    async with httpx.AsyncClient(base_url=get_backend_url(), timeout=10) as session:
        response = await session.get(f"/videos/{video_id}/status")
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest bot/tests/test_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd ai-video-platform
git add bot/client.py bot/tests/test_client.py
git commit -m "feat: telegram bot http client for backend api"
```

---

### Task 4.5: Wire `BOT_DB_PATH` default and confirm full bot test suite passes

**Files:**
- No new files — verification step before moving to glue code.

- [ ] **Step 1: Run the full bot test suite**

Run: `cd ai-video-platform && python -m pytest bot/tests -v`
Expected: 12 passed (5 config + 4 state + 3 client)

- [ ] **Step 2: Run the existing backend test suite to confirm no regression from the new root `pytest.ini`**

Run: `cd ai-video-platform && python -m pytest backend/tests -v`
Expected: all previously-passing backend tests still pass (20 tests per session history)

---

### Task 5: Conversation handlers (`bot/handlers.py`)

**Files:**
- Create: `ai-video-platform/bot/handlers.py`

This task has no automated unit tests — per the spec, the FSM/Telegram-wiring layer is covered by the manual E2E test in Task 7. It depends on `bot/client.py` and `bot/state.py` from Tasks 3–4, which already have unit coverage for the logic they own.

- [ ] **Step 1: Write `bot/handlers.py`**

```python
import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import client, state
from bot.config import get_allowed_user_ids, get_public_base_url

logger = logging.getLogger(__name__)
router = Router()

POLL_INTERVAL_SEC = 5


class GenerateStates(StatesGroup):
    waiting_topic = State()
    waiting_format = State()


def _is_allowed(user_id: int) -> bool:
    return user_id in get_allowed_user_ids()


@router.message(CommandStart())
async def cmd_start(message: Message):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return
    await message.answer(
        "Привет! Команды:\n"
        "/generate — создать видео\n"
        "/history — последние запросы\n"
        "/cancel — отменить текущий ввод"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state_ctx: FSMContext):
    await state_ctx.clear()
    await message.answer("Отменено.")


@router.message(Command("generate"))
async def cmd_generate(message: Message, state_ctx: FSMContext):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return
    await state_ctx.set_state(GenerateStates.waiting_topic)
    await message.answer("Какая тема видео?")


@router.message(GenerateStates.waiting_topic)
async def on_topic(message: Message, state_ctx: FSMContext):
    topic = (message.text or "").strip()
    if not topic:
        await message.answer("Тема не может быть пустой. Напишите тему видео.")
        return
    await state_ctx.update_data(topic=topic)
    await state_ctx.set_state(GenerateStates.waiting_format)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Short (9:16)", callback_data="format:short"),
                InlineKeyboardButton(text="Long (16:9)", callback_data="format:long"),
            ]
        ]
    )
    await message.answer("Какой формат?", reply_markup=keyboard)


@router.callback_query(GenerateStates.waiting_format, F.data.startswith("format:"))
async def on_format(callback: CallbackQuery, state_ctx: FSMContext, bot: Bot):
    fmt = callback.data.split(":", 1)[1]
    data = await state_ctx.get_data()
    topic = data["topic"]
    await state_ctx.clear()
    await callback.message.edit_reply_markup(reply_markup=None)

    try:
        result = await client.create_video(topic, fmt)
    except Exception:
        logger.exception("create_video failed for topic=%r format=%r", topic, fmt)
        await callback.message.answer("Backend недоступен, попробуйте позже.")
        await callback.answer()
        return

    video_id = result["id"]
    state.add_request(video_id, callback.from_user.id, topic, fmt)
    await callback.message.answer(
        "Генерация запущена (~1-5 мин для short / дольше для long). "
        "Сообщу, когда будет готово."
    )
    await callback.answer()
    asyncio.create_task(_poll_and_notify(bot, callback.message.chat.id, video_id))


async def _poll_and_notify(bot: Bot, chat_id: int, video_id: str):
    base_url = get_public_base_url()
    while True:
        await asyncio.sleep(POLL_INTERVAL_SEC)
        try:
            status_data = await client.get_status(video_id)
        except Exception:
            logger.exception("status poll failed for video_id=%s", video_id)
            continue

        status = status_data["status"]
        if status == "completed":
            await bot.send_message(
                chat_id, f"Готово! Скачать: {base_url}/videos/{video_id}/download"
            )
            return
        if status == "failed":
            await bot.send_message(
                chat_id, f"Не получилось: {status_data.get('error')}"
            )
            return


@router.message(Command("history"))
async def cmd_history(message: Message):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    requests = state.get_history(message.from_user.id)
    if not requests:
        await message.answer("История пуста.")
        return

    base_url = get_public_base_url()
    lines = []
    for req in requests:
        try:
            status_data = await client.get_status(req["video_id"])
        except Exception:
            lines.append(f"{req['topic']} ({req['format']}) — статус неизвестен")
            continue

        status = status_data["status"]
        if status == "completed":
            lines.append(
                f"{req['topic']} ({req['format']}) — готово: "
                f"{base_url}/videos/{req['video_id']}/download"
            )
        elif status == "failed":
            lines.append(f"{req['topic']} ({req['format']}) — ошибка: {status_data.get('error')}")
        else:
            lines.append(f"{req['topic']} ({req['format']}) — генерируется")

    await message.answer("\n".join(lines))
```

- [ ] **Step 2: Sanity-check the module imports cleanly**

Run: `cd ai-video-platform && python -c "from bot import handlers"`
Expected: no output, exit code 0 (will fail loudly if `aiogram` isn't installed or there's a syntax error — that's the point of this check)

- [ ] **Step 3: Commit**

```bash
cd ai-video-platform
git add bot/handlers.py
git commit -m "feat: telegram bot conversation handlers"
```

---

### Task 6: Entry point (`bot/main.py`)

**Files:**
- Create: `ai-video-platform/bot/main.py`

- [ ] **Step 1: Write `bot/main.py`**

```python
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.config import get_bot_token
from bot.handlers import router
from bot.state import init_db


def _configure_logging():
    log_path = os.environ.get("BOT_LOG_FILE", "logs/bot.log")
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        filename=log_path,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main():
    load_dotenv()
    _configure_logging()
    init_db()

    bot = Bot(token=get_bot_token())
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Sanity-check the module imports cleanly**

Run: `cd ai-video-platform && python -c "from bot import main"`
Expected: no output, exit code 0

- [ ] **Step 3: Commit**

```bash
cd ai-video-platform
git add bot/main.py
git commit -m "feat: telegram bot entry point"
```

---

### Task 7: Manual end-to-end verification

**Files:** none — this is a manual checklist, not code.

- [ ] **Step 1: Fill in `.env`**

In `ai-video-platform/.env` (not `.env.example`), set:
- `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather) (`/newbot`)
- `TELEGRAM_ALLOWED_USER_IDS` — your numeric Telegram user ID (get it by messaging [@userinfobot](https://t.me/userinfobot))
- `BACKEND_URL=http://localhost:8000`
- `PUBLIC_BASE_URL` — left blank for now, filled in Step 3

- [ ] **Step 2: Start the existing four processes** (per `docs/session-history.md` Сессия 4)

```bash
# Terminal 1
cd ai-video-platform && uvicorn backend.main:app --port 8000

# Terminal 2
cd ai-video-platform && python -m backend.worker
```

(Memurai is already running as a Windows service — no separate Redis terminal needed.)

- [ ] **Step 3: Start a tunnel and capture the public URL**

```bash
# Terminal 3 — pick one
cloudflared tunnel --url http://localhost:8000
# or: ngrok http 8000
```

Copy the printed `https://...` URL into `PUBLIC_BASE_URL` in `.env`, then restart the bot process (Step 4) if it was already running, so it picks up the new value.

- [ ] **Step 4: Start the bot**

```bash
# Terminal 4
cd ai-video-platform && python -m bot.main
```

Expected: no errors printed to console (logs go to `logs/bot.log`); process stays running (long polling).

- [ ] **Step 5: Test the happy path from an allowlisted Telegram account**

1. Open a chat with the bot, send `/start` — expect the greeting with command list.
2. Send `/generate` — expect "Какая тема видео?".
3. Reply with a topic, e.g. "ocean facts" — expect inline buttons Short/Long.
4. Tap "Short (9:16)" — expect "Генерация запущена...".
5. Wait (up to ~5 min) — expect a follow-up message "Готово! Скачать: {PUBLIC_BASE_URL}/videos/{id}/download".
6. Open that link from your phone (same Telegram account's device, or any browser) — expect the MP4 to download/play.

- [ ] **Step 6: Test `/history`**

Send `/history` — expect a list including the request from Step 5 with its download link.

- [ ] **Step 7: Test access control**

From a Telegram account whose user ID is *not* in `TELEGRAM_ALLOWED_USER_IDS`, send `/start` or `/generate` — expect "Доступ запрещён." and no further action.

- [ ] **Step 8: Test backend-unreachable handling**

Stop the `uvicorn` process (Terminal 1), then from the bot try `/generate` → pick a format — expect "Backend недоступен, попробуйте позже." instead of a crash. Restart `uvicorn` afterward.

- [ ] **Step 9: Update session history**

Add an entry to `docs/session-history.md` documenting: date, that the Telegram bot was implemented per `docs/superpowers/plans/2026-06-18-telegram-bot.md`, the tunnel tool chosen, and the manual E2E result (which formats were verified, any issues found).
