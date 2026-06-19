# YouTube OAuth Publishing — Design Spec

**Date:** 2026-06-19
**Type:** Phase 2 addition — публикация готовых видео на YouTube из Telegram-бота

---

## Цель

Дать allowlist-пользователям бота возможность публиковать уже сгенерированные видео прямо на YouTube, без ручного скачивания и загрузки.

## Модель доступа

Общий пул подключённых YouTube-каналов: любой allowlist-пользователь бота может подключить новый канал, и после подключения он становится доступен для публикации **всем** allowlist-пользователям бота (не только тому, кто подключил). Привязки "канал → конкретный пользователь" нет — это осознанное решение, упрощающее модель по сравнению с per-user auth.

---

## Архитектура и поток данных

1. `/connect_channel` в боте → backend генерирует Google OAuth ссылку → пользователь авторизуется в браузере → Google редиректит на backend → backend сохраняет refresh-токен канала в общий пул → backend сам уведомляет пользователя в Telegram о успехе.
2. `/publish` в боте → выбор завершённого видео из истории → выбор канала из общего пула (инлайн-кнопки) → выбор режима метаданных (авто/вручную) → backend ставит задачу в RQ → бот поллит статус и присылает ссылку на YouTube-видео по готовности.

```
[Telegram bot] --HTTP--> [FastAPI backend: routers/youtube.py]
                                |
                works with —— youtube/oauth.py (auth URL, code→token exchange)
                                |
                       youtube/uploader.py --YouTube Data API v3--> [YouTube]
                                |
                            db.sqlite3 (youtube_channels, publishes)
```

Новые модули — аддитивные: `backend/youtube/oauth.py`, `backend/youtube/uploader.py`, `backend/routers/youtube.py`. Существующие `backend/database.py` и `bot/handlers.py` дополняются новыми функциями/хендлерами, без изменения текущих.

---

## Схема данных (дополнение `backend/database.py`, новые таблицы в `db.sqlite3`)

```sql
youtube_channels (
  id                    TEXT PRIMARY KEY,
  channel_id            TEXT NOT NULL,
  channel_title         TEXT NOT NULL,
  refresh_token         TEXT NOT NULL,
  connected_by_user_id  INTEGER NOT NULL,
  created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
)

publishes (
  id               TEXT PRIMARY KEY,
  video_id         TEXT NOT NULL,
  channel_id       TEXT NOT NULL,
  title            TEXT NOT NULL,
  description      TEXT NOT NULL,
  privacy          TEXT NOT NULL DEFAULT 'unlisted',
  status           TEXT NOT NULL DEFAULT 'pending',
  youtube_video_id TEXT,
  error            TEXT,
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at     DATETIME
)
```

Существующая таблица `videos` не меняется.

**OAuth state** (временная привязка "кто начал авторизацию" → `telegram_user_id`) хранится **в памяти процесса backend** (dict с TTL ~10 минут), не в БД — MVP-упрощение. Если backend перезапустится между стартом и завершением OAuth-флоу, пользователь просто повторяет `/connect_channel`.

**Refresh-токены хранятся в SQLite в открытом виде** — как и текущие секреты в `.env`; файл БД не коммитится. Осознанный MVP-риск, не задача "на потом".

---

## Backend: эндпоинты (`backend/routers/youtube.py`)

- `POST /youtube/connect/start` — body `{telegram_user_id}`. Генерирует `state`-токен, кладёт в in-memory dict, возвращает `{"auth_url": ...}` (scope `youtube.upload` + `youtube.readonly`, `access_type=offline`, `prompt=consent`).
- `GET /youtube/oauth/callback?code=&state=` — обменивает code на токены, получает `channel_id`/`channel_title` через `youtube.readonly`, проверяет/удаляет `state`, сохраняет канал в `youtube_channels`. Отдаёт HTML "Готово, возвращайтесь в Telegram" и параллельно шлёт сообщение в Telegram через Bot API (`TELEGRAM_BOT_TOKEN` из общего `.env`) пользователю, начавшему флоу. Просроченный/неизвестный `state` → страница "Ссылка устарела, начните заново через /connect_channel".
- `GET /youtube/channels` — список `{id, channel_title}` всех подключённых каналов.
- `POST /youtube/publish` — body `{video_id, channel_id, title, description}` (privacy фиксирована как `"unlisted"`). Проверяет `video.status == "completed"` (иначе 404), создаёт запись в `publishes`, ставит RQ-задачу `upload_video(publish_id)` с `job_timeout=1800`.
- `GET /youtube/publishes/{id}/status` — для поллинга ботом.

**`backend/youtube/uploader.py`** — `upload_video(publish_id)`: читает `publishes`+`youtube_channels`+`videos`, строит `Credentials` из refresh-токена (`google-auth` сам обновляет access-token), грузит файл через `MediaFileUpload(resumable=True)` + `youtube.videos().insert(...)` с циклом `next_chunk()`. Статусы: `pending` → `uploading` → `completed`/`failed`.

**Новые зависимости** (`backend/requirements.txt`): `google-auth`, `google-auth-oauthlib`, `google-api-python-client`.
**Новые переменные `.env`:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (redirect URI = `{PUBLIC_BASE_URL}/youtube/oauth/callback`, регистрируется в Google Cloud Console).

---

## Бот: команды (дополнение `bot/handlers.py`)

**`/connect_channel`** — allowlist-проверка → `POST /youtube/connect/start` → отдаёт пользователю `auth_url`. Подтверждение об успехе приходит отдельным сообщением от backend, без поллинга в боте.

**`/publish`** (FSM по аналогии с `GenerateStates`):
1. Список завершённых видео пользователя (инлайн-кнопки по теме). Пусто → "Нет готовых видео для публикации."
2. Список каналов общего пула (инлайн-кнопки). Пусто → "Сначала подключите канал: /connect_channel"
3. Кнопки "Автоматически" / "Указать вручную":
   - Авто: `title = topic`, `description = "Сгенерировано AI Video Platform. Тема: {topic}"`, публикация запускается сразу
   - Вручную: бот спрашивает заголовок текстом, затем описание текстом (`-` → оставить пустым)
4. `POST /youtube/publish` → фоновый поллинг `/youtube/publishes/{id}/status` каждые 5с (аналогично `_poll_and_notify`) → ссылка `https://youtube.com/watch?v={youtube_video_id}` или текст ошибки

`/start` дополняется упоминанием новых команд. `/history` не меняется (привязка публикаций к истории — вне рамок).

---

## Обработка ошибок

| Ситуация | Поведение |
|---|---|
| Видео не найдено / не `completed` | `404` в `/youtube/publish`, бот показывает текст ошибки |
| Refresh-токен отозван/истёк (`RefreshError`) | `publishes.status="failed"`, `error="Канал отключён в Google, подключите заново через /connect_channel"` |
| Прочие ошибки YouTube API (квота, сеть) | `status="failed"`, `error=str(exception)` — без классификации/retry |
| `state` не найден/просрочен в OAuth callback | HTML-страница "Ссылка устарела, начните заново" |

---

## Тестирование

- `backend/tests/test_youtube_router.py` — мок google-клиента и RQ; `/connect/start`, `/channels`, `/publish` (включая 404 на незавершённое видео), `/publishes/{id}/status`
- `backend/tests/test_database.py` — дополняется тестами `create_youtube_channel`/`get_channels`/`create_publish`/`update_publish_status`
- `bot/tests/test_handlers.py` — FSM-тесты `/connect_channel` и `/publish` по аналогии с тестами `/generate`
- Ручной E2E: реальный Google-аккаунт, реальная загрузка short-видео с privacy=unlisted

---

## Вне рамок (явно отложено)

- Привязка публикаций к `/history`
- Возможность отключить/удалить канал из пула
- Выбор privacy кроме `unlisted`
- Per-user auth / владение каналом конкретным пользователем (рассматривалось ранее в отдельном неактуальном плане Supabase Auth — отклонено в пользу общего пула каналов)
