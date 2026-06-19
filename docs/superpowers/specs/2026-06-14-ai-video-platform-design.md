# AI Video Content Automation Platform — Design Spec

**Date:** 2026-06-14
**Type:** Local MVP (SaaS billing/auth deferred to Phase 2)
**Language:** English voice-over

---

## Product Goal

A local web tool where the user enters a topic, chooses a video format, and receives a finished MP4. Runs entirely on localhost. No auth, no payments, no cloud storage.

**Phase 2 (post-MVP):** Add Supabase, Stripe, auth, Cloudflare R2, deploy to Vercel + Railway.

---

## MVP Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router, TypeScript) |
| Backend API | Python + FastAPI |
| Video pipeline | Python (openai SDK + MoviePy + FFmpeg) |
| Database | SQLite (single file `db.sqlite3`) |
| Job queue | RQ (Redis Queue) + Redis |
| Video storage | Local `output/` folder |
| Deploy | localhost only |

---

## What MVP Does

```
User opens localhost:3000
  → enters topic + selects format (short | long)
  → clicks "Generate"
  → waits 1–5 minutes (status updates on page)
  → downloads MP4
```

---

## Video Generation Pipeline

```
[User: topic + format]
        │
        ▼
[script_generator.py]  ◄── OpenAI GPT-4o-mini
  Output: title, body, keywords, duration_sec
        │
        ├─────────────────────────────┐
        ▼                             ▼
[voice_synthesizer.py]        [asset_fetcher.py]
◄── OpenAI TTS                ◄── Pexels API
  Output: MP3 + word timings    Output: background video clips
        │                             │
        └──────────────┬──────────────┘
                       ▼
              [video_renderer.py]
              ◄── MoviePy + FFmpeg
                Output: MP4 → saved to output/
```

`voice_synthesizer` and `asset_fetcher` run in parallel via `asyncio.gather`.

### Video Formats

| Format | Aspect ratio | Duration | Target |
|--------|-------------|----------|--------|
| short  | 9:16        | up to 60s | TikTok, Reels, YouTube Shorts |
| long   | 16:9        | 3–15 min  | YouTube |

### API Cost per video

| Format | Cost |
|--------|------|
| Short  | ~$0.02 |
| Long   | ~$0.17 |

---

## Data Models (Python)

```python
@dataclass
class PipelineInput:
    topic: str
    format: Literal['short', 'long']
    job_id: str

@dataclass
class Script:
    title: str
    body: str
    keywords: list[str]
    duration_sec: int

@dataclass
class VoiceOutput:
    audio_path: str
    word_timings: list[dict]  # {word, start_sec, end_sec}

@dataclass
class Assets:
    video_clips: list[dict]   # {path, duration_sec}

@dataclass
class RenderOutput:
    video_path: str
    format: str
```

---

## SQLite Schema

```sql
videos (
  id          TEXT PRIMARY KEY,
  topic       TEXT NOT NULL,
  format      TEXT NOT NULL,       -- 'short' | 'long'
  status      TEXT NOT NULL,       -- 'pending' | 'processing' | 'completed' | 'failed'
  video_path  TEXT,                -- local path to MP4
  error       TEXT,
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME
)
```

---

## Async Job Flow

```
1. User submits form → POST /api/videos
2. FastAPI creates SQLite record (status: pending) → enqueues RQ job
3. RQ worker runs pipeline → updates status to processing
4. On success → saves MP4 to output/ → updates status to completed + video_path
5. On failure → updates status to failed + error message
6. Frontend polls GET /api/videos/{id}/status every 3s → shows download when ready
```

---

## Project Structure

```
ai-video-platform/
├── frontend/                        # Next.js app (port 3000)
│   ├── app/
│   │   ├── page.tsx                 # generation form
│   │   └── api/
│   │       └── proxy/route.ts       # proxies to FastAPI
│   └── components/
│       ├── GenerateForm.tsx
│       └── StatusPoller.tsx
│
├── backend/                         # FastAPI app (port 8000)
│   ├── main.py
│   ├── routers/
│   │   └── videos.py                # POST /videos, GET /videos/{id}/status
│   ├── pipeline/
│   │   ├── script_generator.py
│   │   ├── voice_synthesizer.py
│   │   ├── asset_fetcher.py
│   │   └── video_renderer.py
│   ├── worker.py                    # RQ worker
│   ├── database.py                  # SQLite connection + queries
│   └── requirements.txt
│
├── output/                          # generated MP4 files
├── temp/                            # temporary audio + clips (auto-cleaned)
└── .env                             # OPENAI_API_KEY, PEXELS_API_KEY
```

---

## Running Locally

```bash
# Terminal 1 — Redis
redis-server

# Terminal 2 — FastAPI
cd backend && uvicorn main:app --reload --port 8000

# Terminal 3 — RQ Worker
cd backend && rq worker

# Terminal 4 — Next.js
cd frontend && npm run dev
```

Open `http://localhost:3000`

---

## Error Handling

| Error | Handling |
|-------|---------|
| OpenAI rate limit | Retry with exponential backoff, 3 attempts |
| Pexels returns nothing | Fall back to gradient background, pipeline continues |
| MoviePy render failure | Save script + audio to `temp/`, mark job `failed`, show error in UI |

---

## Testing

| Type | What is tested |
|------|---------------|
| Unit | `script_generator` — output shape, duration per format |
| Unit | `asset_fetcher` — gradient fallback on empty Pexels response |
| Integration | Full pipeline with mocked OpenAI and Pexels APIs |
| Integration | FastAPI endpoints with test client |

---

## Phase 2 (Post-MVP Additions)

- Replace SQLite → Supabase (PostgreSQL)
- Add Supabase Auth (user accounts)
- Add Stripe pay-as-you-go billing ($0.50 short / $2.00 long)
- Replace local `output/` → Cloudflare R2
- Deploy: Vercel (frontend) + Railway (backend + worker)
- Add YouTube OAuth publishing
