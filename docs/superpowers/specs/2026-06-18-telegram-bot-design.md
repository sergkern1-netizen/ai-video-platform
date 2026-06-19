# Telegram Bot Interface — Design Spec

**Date:** 2026-06-18
**Type:** New interface to existing AI Video Platform MVP (no backend changes required)

---

## Product Goal

Allow a small allowlist of Telegram users to generate videos (short/long) through a chat bot instead of (or in addition to) the Next.js web UI, and receive a download link when ready, from anywhere — including their phone, not just the local machine.

---

## Architecture

The bot is a thin HTTP client to the existing FastAPI backend. It does not touch backend code or schema.

```
[Telegram] ←long polling→ [bot/main.py] --HTTP--> [FastAPI :8000] --RQ--> [worker] --MoviePy--> output/
                                                         ↑
                                          [ngrok / cloudflared tunnel] (public URL for download links)
```

Six processes total for full operation:
1. Memurai (Windows service, already running — Redis-compatible)
2. `uvicorn backend.main:app --port 8000`
3. `python -m backend.worker` (RQ SimpleWorker)
4. `cloudflared tunnel --url http://localhost:8000` (or `ngrok http 8000`) — gives a public HTTPS URL forwarding to the local backend
5. `python -m bot.main` (aiogram long polling)
6. (optional) `npm run dev` in `frontend/` — web UI still works independently

The tunnel is only needed so that download links work from devices other than the host machine (e.g. a phone). The bot's own connection to Telegram (long polling) does not require a public address.

---

## Library Choice

**aiogram 3.x** — async, built-in FSM (Finite State Machine) support for the multi-step `/generate` conversation, actively maintained.

---

## Access Control

- Allowlist of Telegram `user_id`s, configured via `.env`: `TELEGRAM_ALLOWED_USER_IDS=123456,789012` (comma-separated integers)
- Any message from a `user_id` not in the list gets a terse "access denied" reply; no further action taken, no details leaked about the bot's capabilities
- Bot token: `TELEGRAM_BOT_TOKEN` in `.env`
- Public base URL for download links: `PUBLIC_BASE_URL` in `.env` (manually updated when the tunnel restarts and issues a new address, unless using a paid/stable tunnel subdomain)

---

## Conversational Flow (FSM)

```
/start     → greeting + short list of available commands
/generate  → bot: "What's the video topic?"
  [user replies with topic text]
             → bot shows inline buttons: [Short (9:16)] [Long (16:9)]
  [user taps a button]
             → POST /videos/ {topic, format} → video_id
             → record (video_id, user_id, topic, format) in bot_state.db
             → bot: "Generation started (~1-5 min for short, longer for long). I'll let you know when it's ready."
             → background asyncio task: poll GET /videos/{id}/status every 5s
  on status == "completed"
             → bot: "Done! Download: {PUBLIC_BASE_URL}/videos/{id}/download"
  on status == "failed"
             → bot: "Failed: {error}"
/history   → show the user's last 5 requests with current status (see below)
/cancel    → resets FSM state if the user is mid-flow (waiting for topic/format input)
```

FSM state and active polling tasks live in the bot process memory (aiogram `MemoryStorage` + an in-memory `dict[video_id, chat_id]` for active polls). If the bot restarts while a video is generating, that specific poll-and-notify is lost — the video still finishes and remains reachable via `/history` or the download endpoint; this matches the MVP's existing "no complex fault tolerance" posture (see `docs/superpowers/specs/2026-06-14-ai-video-platform-design.md`).

---

## History (`/history`)

The bot keeps its own lightweight record of which `video_id`s each `user_id` requested, in a separate SQLite file `bot/bot_state.db` (kept apart from the backend's `db.sqlite3` to avoid touching its schema/API):

```sql
requests (
  video_id    TEXT PRIMARY KEY,
  user_id     INTEGER NOT NULL,
  topic       TEXT NOT NULL,
  format      TEXT NOT NULL,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

A row is inserted immediately after a successful `POST /videos/`.

`/history` shows the calling user's last 5 requests (topic, format, date). For each, the bot calls `GET /videos/{id}/status` live to show current state:
- `completed` → download link
- `pending`/`processing` → "still generating"
- `failed` → "failed: {error}"

---

## Error Handling

| Error | Handling |
|-------|---------|
| Backend HTTP unreachable/timeout | Bot replies "Backend unavailable, try again later", does not crash |
| Empty/invalid topic text | Bot re-prompts for topic |
| Message from non-allowlisted user_id | Silent generic refusal, no details |
| Telegram API errors (rate limit, etc.) | aiogram's default retry/backoff; log and continue |

All bot logs go to `ai-video-platform/logs/bot.log` (gitignored), matching the existing logging convention for the other processes.

---

## Project Structure (new)

```
ai-video-platform/
├── bot/
│   ├── main.py            # entry point, long polling startup
│   ├── handlers.py        # /start, /generate, /history, /cancel
│   ├── client.py          # httpx-based client to FastAPI backend
│   ├── state.py           # SQLite bot_state.db — requests table
│   ├── config.py          # loads TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, PUBLIC_BASE_URL
│   └── requirements.txt   # aiogram, httpx
```

New `.env` variables: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`, `PUBLIC_BASE_URL`.

---

## Testing

| Type | What is tested |
|------|---------------|
| Unit | `bot/client.py` — HTTP responses mocked (httpx mock transport), correct status parsing |
| Unit | `bot/state.py` — insert/read requests in `bot_state.db` |
| Manual E2E | Message the bot from an allowlisted phone account, complete `/generate` flow, receive working download link; confirm refusal for a non-allowlisted user_id |

---

## Out of Scope (deferred)

- Webhook mode for the bot itself (long polling is sufficient; bot doesn't need a public address for Telegram updates)
- Persisting active poll tasks across bot restarts
- Web UI changes (Next.js frontend is untouched and still works independently)
- Stable/permanent tunnel domain (acceptable to manually update `PUBLIC_BASE_URL` on tunnel restart for MVP)
