дав# AI Video Platform MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web tool where a user enters a topic, clicks Generate, waits 1–5 minutes, and downloads a finished MP4 video with AI-generated script, voice-over, and background footage.

**Architecture:** Next.js frontend (port 3000) talks to FastAPI backend (port 8000) via URL rewrites. FastAPI enqueues a job in Redis via RQ. An RQ worker runs the Python pipeline (GPT-4o-mini → OpenAI TTS + Pexels → MoviePy) and saves the MP4 locally. The frontend polls for status every 3 seconds.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, RQ + Redis, MoviePy + Pillow + FFmpeg, OpenAI SDK, httpx, Next.js 14 (TypeScript), pytest

---

## File Map

```
ai-video-platform/
├── backend/
│   ├── main.py                          # FastAPI app, CORS, startup
│   ├── database.py                      # SQLite init + CRUD
│   ├── worker.py                        # RQ worker entry point
│   ├── routers/
│   │   └── videos.py                    # POST /videos/, GET /videos/{id}/status, GET /videos/{id}/download
│   ├── pipeline/
│   │   ├── runner.py                    # orchestrates all modules, called by RQ
│   │   ├── script_generator.py          # GPT-4o-mini → Script dataclass
│   │   ├── voice_synthesizer.py         # OpenAI TTS → MP3 file
│   │   ├── asset_fetcher.py             # Pexels API → local video clips
│   │   └── video_renderer.py            # MoviePy → MP4
│   ├── tests/
│   │   ├── test_database.py
│   │   ├── test_script_generator.py
│   │   ├── test_voice_synthesizer.py
│   │   ├── test_asset_fetcher.py
│   │   ├── test_video_renderer.py
│   │   └── test_videos_router.py
│   └── requirements.txt
├── frontend/
│   ├── next.config.js                   # rewrites /api/* → localhost:8000/*
│   ├── app/
│   │   └── page.tsx                     # renders GenerateForm or StatusPoller
│   └── components/
│       ├── GenerateForm.tsx             # topic + format form, POST to API
│       └── StatusPoller.tsx             # polls status, shows download link
├── output/                              # generated MP4 files (git-ignored)
├── temp/                                # temporary audio + video clips (git-ignored)
└── .env                                 # OPENAI_API_KEY, PEXELS_API_KEY
```

---

## Task 1: Project Setup

**Files:**
- Create: `backend/requirements.txt`
- Create: `.env.example`
- Create: `backend/conftest.py`
- Create: `output/.gitkeep`
- Create: `temp/.gitkeep`

- [ ] **Step 1: Create root directory and backend folder**

```bash
mkdir -p ai-video-platform/backend/routers
mkdir -p ai-video-platform/backend/pipeline
mkdir -p ai-video-platform/backend/tests
mkdir -p ai-video-platform/output
mkdir -p ai-video-platform/temp
touch ai-video-platform/output/.gitkeep
touch ai-video-platform/temp/.gitkeep
```

- [ ] **Step 2: Write requirements.txt**

Create `backend/requirements.txt`:
```
fastapi==0.111.0
uvicorn[standard]==0.30.1
openai==1.35.0
httpx==0.27.0
moviepy==1.0.3
pillow==10.4.0
rq==1.16.2
redis==5.0.7
python-dotenv==1.0.1
pytest==8.2.2
```

- [ ] **Step 3: Install backend dependencies**

```bash
cd ai-video-platform/backend
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 4: Create .env.example**

Create `.env.example` at project root:
```
OPENAI_API_KEY=sk-...
PEXELS_API_KEY=...
DB_PATH=db.sqlite3
REDIS_URL=redis://localhost:6379
```

Copy it to `.env` and fill in real keys:
```bash
cp .env.example .env
```

- [ ] **Step 5: Create conftest.py for pytest**

Create `backend/conftest.py`:
```python
import os
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("PEXELS_API_KEY", "test-key")
os.environ.setdefault("DB_PATH", ":memory:")
```

- [ ] **Step 6: Create __init__.py files**

```bash
touch ai-video-platform/backend/__init__.py
touch ai-video-platform/backend/routers/__init__.py
touch ai-video-platform/backend/pipeline/__init__.py
touch ai-video-platform/backend/tests/__init__.py
```

- [ ] **Step 7: Verify Python version**

```bash
python --version
```

Expected: Python 3.11.x or higher.

- [ ] **Step 8: Verify FFmpeg is installed**

```bash
ffmpeg -version
```

Expected: version line printed. If missing, install: https://ffmpeg.org/download.html and add to PATH.

- [ ] **Step 9: Commit**

```bash
cd ai-video-platform
git init
echo "output/*.mp4" >> .gitignore
echo "temp/" >> .gitignore
echo ".env" >> .gitignore
echo "__pycache__/" >> .gitignore
echo ".pytest_cache/" >> .gitignore
git add .
git commit -m "feat: project scaffold"
```

---

## Task 2: Database Layer

**Files:**
- Create: `backend/database.py`
- Create: `backend/tests/test_database.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_database.py`:
```python
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.database import init_db, create_video, get_video, update_video_status

@pytest.fixture(autouse=True)
def fresh_db(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_file)
    init_db()
    yield

def test_create_video_returns_pending():
    video = create_video("vid-1", "AI trends", "short")
    assert video["id"] == "vid-1"
    assert video["status"] == "pending"
    assert video["topic"] == "AI trends"
    assert video["format"] == "short"

def test_get_video_returns_none_for_unknown():
    assert get_video("nonexistent") is None

def test_update_status_to_processing():
    create_video("vid-2", "History", "long")
    update_video_status("vid-2", "processing")
    video = get_video("vid-2")
    assert video["status"] == "processing"

def test_update_status_to_completed_sets_path():
    create_video("vid-3", "Science", "short")
    update_video_status("vid-3", "completed", video_path="output/vid-3.mp4")
    video = get_video("vid-3")
    assert video["status"] == "completed"
    assert video["video_path"] == "output/vid-3.mp4"
    assert video["completed_at"] is not None

def test_update_status_to_failed_sets_error():
    create_video("vid-4", "Math", "short")
    update_video_status("vid-4", "failed", error="OpenAI rate limit")
    video = get_video("vid-4")
    assert video["status"] == "failed"
    assert video["error"] == "OpenAI rate limit"
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd ai-video-platform
python -m pytest backend/tests/test_database.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — database.py does not exist yet.

- [ ] **Step 3: Implement database.py**

Create `backend/database.py`:
```python
import sqlite3
import os
from contextlib import contextmanager

def _db_path() -> str:
    return os.environ.get("DB_PATH", "db.sqlite3")

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
            CREATE TABLE IF NOT EXISTS videos (
                id           TEXT PRIMARY KEY,
                topic        TEXT NOT NULL,
                format       TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'pending',
                video_path   TEXT,
                error        TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
            )
        """)

def create_video(video_id: str, topic: str, format: str) -> dict:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO videos (id, topic, format) VALUES (?, ?, ?)",
            (video_id, topic, format),
        )
    return get_video(video_id)

def get_video(video_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

def update_video_status(
    video_id: str,
    status: str,
    video_path: str = None,
    error: str = None,
):
    with _conn() as conn:
        if status == "completed":
            conn.execute(
                "UPDATE videos SET status=?, video_path=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, video_path, video_id),
            )
        elif status == "failed":
            conn.execute(
                "UPDATE videos SET status=?, error=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, error, video_id),
            )
        else:
            conn.execute(
                "UPDATE videos SET status=? WHERE id=?",
                (status, video_id),
            )
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest backend/tests/test_database.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py backend/tests/test_database.py
git commit -m "feat: SQLite database layer with CRUD for videos"
```

---

## Task 3: Script Generator

**Files:**
- Create: `backend/pipeline/script_generator.py`
- Create: `backend/tests/test_script_generator.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_script_generator.py`:
```python
import json
from unittest.mock import patch, MagicMock
from backend.pipeline.script_generator import generate_script, Script

def _mock_openai(content: str):
    mock = MagicMock()
    mock.choices[0].message.content = content
    return mock

def test_generate_script_short_returns_script_dataclass():
    payload = json.dumps({
        "title": "How to Learn Python Fast",
        "body": "Python is one of the most popular programming languages today.",
        "keywords": ["python", "programming", "learn"],
        "duration_sec": 50,
    })
    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_openai(payload)
        script = generate_script("How to learn Python", "short")

    assert isinstance(script, Script)
    assert script.title == "How to Learn Python Fast"
    assert "Python" in script.body
    assert "python" in script.keywords
    assert script.duration_sec == 50

def test_generate_script_long_requests_600_seconds():
    payload = json.dumps({
        "title": "The Full History of Rome",
        "body": "Rome was not built in a day. " * 100,
        "keywords": ["rome", "history", "ancient"],
        "duration_sec": 600,
    })
    captured = {}
    def capture(*args, **kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return _mock_openai(payload)

    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = capture
        script = generate_script("History of Rome", "long")

    assert script.duration_sec == 600
    user_msg = captured["messages"][1]["content"]
    assert "10 minutes" in user_msg or "600" in user_msg

def test_generate_script_retries_on_invalid_json():
    bad_response = _mock_openai("not valid json {{")
    good_payload = json.dumps({
        "title": "Retry Works",
        "body": "Body text here.",
        "keywords": ["retry"],
        "duration_sec": 50,
    })
    good_response = _mock_openai(good_payload)

    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = [
            bad_response, good_response
        ]
        script = generate_script("test topic", "short")

    assert script.title == "Retry Works"
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest backend/tests/test_script_generator.py -v
```

Expected: ImportError — module does not exist yet.

- [ ] **Step 3: Implement script_generator.py**

Create `backend/pipeline/script_generator.py`:
```python
import json
import os
from dataclasses import dataclass
from openai import OpenAI

@dataclass
class Script:
    title: str
    body: str
    keywords: list[str]
    duration_sec: int

_SHORT_PROMPT = """Write a YouTube Shorts / TikTok video script about: "{topic}"

Format: vertical short video, under 60 seconds
Target: ~120 words

Respond with JSON only — no markdown, no explanation:
{{
  "title": "video title (max 60 chars)",
  "body": "the full narration text",
  "keywords": ["word1", "word2", "word3"],
  "duration_sec": 50
}}"""

_LONG_PROMPT = """Write a YouTube video script about: "{topic}"

Format: horizontal YouTube video, 10 minutes
Target: ~1500 words

Respond with JSON only — no markdown, no explanation:
{{
  "title": "video title (max 70 chars)",
  "body": "the full narration text",
  "keywords": ["word1", "word2", "word3"],
  "duration_sec": 600
}}"""

def generate_script(topic: str, format: str, max_retries: int = 3) -> Script:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = _SHORT_PROMPT if format == "short" else _LONG_PROMPT

    for attempt in range(max_retries):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional video script writer. Always respond with valid JSON only."},
                {"role": "user", "content": prompt.format(topic=topic)},
            ],
            temperature=0.7,
        )
        raw = response.choices[0].message.content.strip()
        try:
            data = json.loads(raw)
            return Script(
                title=data["title"],
                body=data["body"],
                keywords=data["keywords"],
                duration_sec=data["duration_sec"],
            )
        except (json.JSONDecodeError, KeyError):
            if attempt == max_retries - 1:
                raise ValueError(f"Script generator failed after {max_retries} attempts. Last response: {raw[:200]}")
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest backend/tests/test_script_generator.py -v
```

Expected: 3 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/script_generator.py backend/tests/test_script_generator.py
git commit -m "feat: script generator using GPT-4o-mini"
```

---

## Task 4: Voice Synthesizer

**Files:**
- Create: `backend/pipeline/voice_synthesizer.py`
- Create: `backend/tests/test_voice_synthesizer.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_voice_synthesizer.py`:
```python
import os
from unittest.mock import patch, MagicMock
from backend.pipeline.script_generator import Script
from backend.pipeline.voice_synthesizer import synthesize_voice, VoiceOutput

def _make_script(body="Hello world this is a test script for synthesis."):
    return Script(title="Test", body=body, keywords=["test"], duration_sec=50)

def test_synthesize_voice_creates_mp3_file(tmp_path):
    mock_response = MagicMock()
    mock_response.stream_to_file = MagicMock()

    with patch("backend.pipeline.voice_synthesizer.OpenAI") as MockClient, \
         patch("backend.pipeline.voice_synthesizer.AudioFileClip") as MockAudio:
        MockClient.return_value.audio.speech.create.return_value = mock_response
        MockAudio.return_value.duration = 30.0
        MockAudio.return_value.close = MagicMock()

        result = synthesize_voice(_make_script(), "job-123", audio_dir=str(tmp_path))

    assert isinstance(result, VoiceOutput)
    assert result.audio_path.endswith(".mp3")
    assert "job-123" in result.audio_path

def test_synthesize_voice_estimates_timings(tmp_path):
    mock_response = MagicMock()
    mock_response.stream_to_file = MagicMock()

    with patch("backend.pipeline.voice_synthesizer.OpenAI") as MockClient, \
         patch("backend.pipeline.voice_synthesizer.AudioFileClip") as MockAudio:
        MockClient.return_value.audio.speech.create.return_value = mock_response
        MockAudio.return_value.duration = 20.0
        MockAudio.return_value.close = MagicMock()

        result = synthesize_voice(
            _make_script("one two three four five six seven eight nine ten"),
            "job-456",
            audio_dir=str(tmp_path),
        )

    assert len(result.word_timings) > 0
    first = result.word_timings[0]
    assert "text" in first
    assert "start" in first
    assert "end" in first
    assert first["start"] == 0.0
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest backend/tests/test_voice_synthesizer.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement voice_synthesizer.py**

Create `backend/pipeline/voice_synthesizer.py`:
```python
import os
from dataclasses import dataclass
from openai import OpenAI
from moviepy.editor import AudioFileClip
from backend.pipeline.script_generator import Script

@dataclass
class VoiceOutput:
    audio_path: str
    word_timings: list[dict]  # [{text, start, end}]

def synthesize_voice(script: Script, job_id: str, audio_dir: str = "temp") -> VoiceOutput:
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, f"{job_id}.mp3")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=script.body,
    )
    response.stream_to_file(audio_path)

    clip = AudioFileClip(audio_path)
    duration = clip.duration
    clip.close()

    word_timings = _estimate_timings(script.body, duration)
    return VoiceOutput(audio_path=audio_path, word_timings=word_timings)

def _estimate_timings(text: str, total_duration: float) -> list[dict]:
    words = text.split()
    chunk_size = 8
    chunks = [
        " ".join(words[i : i + chunk_size])
        for i in range(0, len(words), chunk_size)
    ]
    if not chunks:
        return []
    time_per_chunk = total_duration / len(chunks)
    return [
        {
            "text": chunk,
            "start": round(i * time_per_chunk, 2),
            "end": round((i + 1) * time_per_chunk, 2),
        }
        for i, chunk in enumerate(chunks)
    ]
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest backend/tests/test_voice_synthesizer.py -v
```

Expected: 2 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/voice_synthesizer.py backend/tests/test_voice_synthesizer.py
git commit -m "feat: voice synthesizer using OpenAI TTS"
```

---

## Task 5: Asset Fetcher

**Files:**
- Create: `backend/pipeline/asset_fetcher.py`
- Create: `backend/tests/test_asset_fetcher.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_asset_fetcher.py`:
```python
import pytest
from unittest.mock import patch, MagicMock
from backend.pipeline.asset_fetcher import fetch_assets, Assets

def _mock_pexels_response(videos: list):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"videos": videos}
    return mock

def test_fetch_assets_returns_empty_when_pexels_fails():
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get:
        mock_get.return_value = _mock_pexels_response([])
        assets = fetch_assets(["unknown_xyz_topic_abc"], 60)
    assert isinstance(assets, Assets)
    assert assets.video_clips == []

def test_fetch_assets_returns_empty_on_http_error():
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get:
        mock_get.side_effect = Exception("connection refused")
        assets = fetch_assets(["nature"], 60)
    assert assets.video_clips == []

def test_fetch_assets_returns_clips_on_success(tmp_path):
    mock_video = {
        "id": 999,
        "duration": 15,
        "video_files": [
            {"width": 1920, "height": 1080, "link": "https://example.com/clip.mp4"}
        ],
    }
    fake_content = b"fake video bytes"

    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get, \
         patch("backend.pipeline.asset_fetcher._download_clip") as mock_dl:
        mock_get.return_value = _mock_pexels_response([mock_video])
        mock_dl.return_value = str(tmp_path / "999.mp4")

        assets = fetch_assets(["nature", "forest"], 60, clip_dir=str(tmp_path))

    assert len(assets.video_clips) == 1
    assert assets.video_clips[0]["duration_sec"] == 15
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest backend/tests/test_asset_fetcher.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement asset_fetcher.py**

Create `backend/pipeline/asset_fetcher.py`:
```python
import os
from dataclasses import dataclass, field
import httpx

PEXELS_API_URL = "https://api.pexels.com/videos/search"

@dataclass
class Assets:
    video_clips: list[dict] = field(default_factory=list)  # [{path, duration_sec}]

def fetch_assets(keywords: list[str], duration_sec: int, clip_dir: str = "temp") -> Assets:
    query = " ".join(keywords[:2])
    try:
        resp = httpx.get(
            PEXELS_API_URL,
            headers={"Authorization": os.environ["PEXELS_API_KEY"]},
            params={"query": query, "per_page": 5, "min_duration": 5},
            timeout=15,
        )
        videos = resp.json().get("videos", [])
    except Exception:
        return Assets()

    if not videos:
        return Assets()

    os.makedirs(clip_dir, exist_ok=True)
    clips = []
    for video in videos:
        files = sorted(
            video["video_files"],
            key=lambda f: f.get("width", 0),
            reverse=True,
        )
        best = next((f for f in files if f.get("width", 0) >= 1080), files[0])
        clip_path = os.path.join(clip_dir, f"{video['id']}.mp4")
        try:
            _download_clip(best["link"], clip_path)
            clips.append({"path": clip_path, "duration_sec": video["duration"]})
        except Exception:
            continue

    return Assets(video_clips=clips)

def _download_clip(url: str, path: str) -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            with open(path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest backend/tests/test_asset_fetcher.py -v
```

Expected: 3 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/asset_fetcher.py backend/tests/test_asset_fetcher.py
git commit -m "feat: asset fetcher with Pexels API and empty-result fallback"
```

---

## Task 6: Video Renderer

**Files:**
- Create: `backend/pipeline/video_renderer.py`
- Create: `backend/tests/test_video_renderer.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_video_renderer.py`:
```python
import os
import pytest
from unittest.mock import patch, MagicMock
from backend.pipeline.script_generator import Script
from backend.pipeline.voice_synthesizer import VoiceOutput
from backend.pipeline.asset_fetcher import Assets
from backend.pipeline.video_renderer import render_video

def _make_inputs(clips=None):
    script = Script(
        title="Test Video",
        body="This is a test body for our video renderer.",
        keywords=["test"],
        duration_sec=10,
    )
    voice = VoiceOutput(
        audio_path="temp/test.mp3",
        word_timings=[
            {"text": "This is a test body", "start": 0.0, "end": 5.0},
            {"text": "for our video renderer.", "start": 5.0, "end": 10.0},
        ],
    )
    assets = Assets(video_clips=clips or [])
    return script, voice, assets

def test_render_video_uses_gradient_when_no_clips(tmp_path):
    script, voice, assets = _make_inputs(clips=[])
    output_path = str(tmp_path / "out.mp4")

    with patch("backend.pipeline.video_renderer.AudioFileClip") as MockAudio, \
         patch("backend.pipeline.video_renderer.ColorClip") as MockColor, \
         patch("backend.pipeline.video_renderer.CompositeVideoClip") as MockComposite, \
         patch("backend.pipeline.video_renderer._make_subtitle_clip") as MockSub:
        MockAudio.return_value.duration = 10.0
        MockColor.return_value.duration = 10.0
        MockComposite.return_value.set_audio.return_value = MagicMock()
        MockComposite.return_value.set_audio.return_value.write_videofile = MagicMock()
        MockSub.return_value = MagicMock()

        render_video(script, voice, assets, "short", output_path)

    MockColor.assert_called_once()

def test_render_video_uses_clips_when_available(tmp_path):
    script, voice, assets = _make_inputs(
        clips=[{"path": "temp/clip1.mp4", "duration_sec": 15}]
    )
    output_path = str(tmp_path / "out.mp4")

    with patch("backend.pipeline.video_renderer.AudioFileClip") as MockAudio, \
         patch("backend.pipeline.video_renderer.VideoFileClip") as MockVFC, \
         patch("backend.pipeline.video_renderer.ColorClip") as MockColor, \
         patch("backend.pipeline.video_renderer.CompositeVideoClip") as MockComposite, \
         patch("backend.pipeline.video_renderer._make_subtitle_clip") as MockSub:
        MockAudio.return_value.duration = 10.0
        mock_clip = MagicMock()
        mock_clip.duration = 15.0
        mock_clip.resize.return_value = mock_clip
        mock_clip.subclip.return_value = mock_clip
        MockVFC.return_value = mock_clip
        MockComposite.return_value.set_audio.return_value = MagicMock()
        MockComposite.return_value.set_audio.return_value.write_videofile = MagicMock()
        MockSub.return_value = MagicMock()

        render_video(script, voice, assets, "short", output_path)

    MockColor.assert_not_called()
    MockVFC.assert_called_once_with("temp/clip1.mp4")
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest backend/tests/test_video_renderer.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement video_renderer.py**

Create `backend/pipeline/video_renderer.py`:
```python
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
)
from backend.pipeline.script_generator import Script
from backend.pipeline.voice_synthesizer import VoiceOutput
from backend.pipeline.asset_fetcher import Assets

_SIZES = {
    "short": (1080, 1920),
    "long": (1920, 1080),
}

def render_video(
    script: Script,
    voice: VoiceOutput,
    assets: Assets,
    format: str,
    output_path: str,
) -> None:
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    size = _SIZES[format]

    audio = AudioFileClip(voice.audio_path)
    duration = audio.duration

    background = _build_background(assets, size, duration)
    subtitle_clips = [
        _make_subtitle_clip(t["text"], size, t["end"] - t["start"])
        .set_start(t["start"])
        .set_end(t["end"])
        for t in voice.word_timings
    ]

    final = CompositeVideoClip([background] + subtitle_clips, size=size)
    final = final.set_audio(audio)
    final.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

def _build_background(assets: Assets, size: tuple, duration: float):
    if not assets.video_clips:
        return ColorClip(size=size, color=[20, 20, 40], duration=duration)

    clip_path = assets.video_clips[0]["path"]
    clip = VideoFileClip(clip_path)
    clip = clip.resize(size)
    if clip.duration < duration:
        clip = clip.loop(duration=duration)
    else:
        clip = clip.subclip(0, duration)
    return clip

def _make_subtitle_clip(text: str, size: tuple, duration: float) -> ImageClip:
    w, h = size
    font_size = 60 if w == 1080 else 42
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    words = text.split()
    lines, current = [], []
    for word in words:
        current.append(word)
        bbox = draw.textbbox((0, 0), " ".join(current), font=font)
        if bbox[2] > w - 80:
            current.pop()
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))

    line_height = font_size + 10
    y = h - len(lines) * line_height - 60
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (w - bbox[2]) // 2
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0, 200), font=font)
        draw.text((x, y), line, fill=(255, 255, 255, 255), font=font)
        y += line_height

    return ImageClip(np.array(img), duration=duration, ismask=False)
```

- [ ] **Step 4: Run — expect pass**

```bash
python -m pytest backend/tests/test_video_renderer.py -v
```

Expected: 2 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/video_renderer.py backend/tests/test_video_renderer.py
git commit -m "feat: video renderer with MoviePy, Pillow subtitles, gradient fallback"
```

---

## Task 7: Pipeline Runner

**Files:**
- Create: `backend/pipeline/runner.py`

- [ ] **Step 1: Implement runner.py**

Create `backend/pipeline/runner.py`:
```python
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

import backend.database as db
from backend.pipeline.asset_fetcher import fetch_assets
from backend.pipeline.script_generator import generate_script
from backend.pipeline.video_renderer import render_video
from backend.pipeline.voice_synthesizer import synthesize_voice

@dataclass
class PipelineInput:
    topic: str
    format: Literal["short", "long"]
    job_id: str

def run_pipeline(pipeline_input: PipelineInput) -> None:
    job_id = pipeline_input.job_id
    try:
        db.update_video_status(job_id, "processing")

        script = generate_script(pipeline_input.topic, pipeline_input.format)

        with ThreadPoolExecutor(max_workers=2) as executor:
            voice_future = executor.submit(synthesize_voice, script, job_id)
            assets_future = executor.submit(
                fetch_assets, script.keywords, script.duration_sec
            )
            voice = voice_future.result()
            assets = assets_future.result()

        os.makedirs("output", exist_ok=True)
        output_path = os.path.join("output", f"{job_id}.mp4")
        render_video(script, voice, assets, pipeline_input.format, output_path)

        db.update_video_status(job_id, "completed", video_path=output_path)

    except Exception as exc:
        db.update_video_status(job_id, "failed", error=str(exc))
        raise
```

- [ ] **Step 2: Verify imports resolve**

```bash
cd ai-video-platform
python -c "from backend.pipeline.runner import run_pipeline, PipelineInput; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/pipeline/runner.py
git commit -m "feat: pipeline runner orchestrating all modules"
```

---

## Task 8: FastAPI App + RQ Worker

**Files:**
- Create: `backend/main.py`
- Create: `backend/routers/videos.py`
- Create: `backend/worker.py`
- Create: `backend/tests/test_videos_router.py`

- [ ] **Step 1: Write failing router tests**

Create `backend/tests/test_videos_router.py`:
```python
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

with patch("backend.routers.videos.Redis"), patch("backend.routers.videos.Queue"):
    from backend.main import app

client = TestClient(app)

def test_create_video_returns_id():
    with patch("backend.routers.videos.db.create_video") as mock_create, \
         patch("backend.routers.videos._queue") as mock_q:
        mock_create.return_value = {"id": "abc", "status": "pending"}
        resp = client.post("/videos/", json={"topic": "AI news", "format": "short"})

    assert resp.status_code == 200
    assert "id" in resp.json()
    mock_q.enqueue.assert_called_once()

def test_create_video_rejects_invalid_format():
    resp = client.post("/videos/", json={"topic": "AI news", "format": "bad"})
    assert resp.status_code == 422

def test_get_status_returns_video():
    with patch("backend.routers.videos.db.get_video") as mock_get:
        mock_get.return_value = {
            "id": "abc", "topic": "AI news", "format": "short",
            "status": "processing", "video_path": None, "error": None,
            "created_at": "2026-06-14", "completed_at": None,
        }
        resp = client.get("/videos/abc/status")

    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"

def test_get_status_returns_404_for_unknown():
    with patch("backend.routers.videos.db.get_video", return_value=None):
        resp = client.get("/videos/nonexistent/status")
    assert resp.status_code == 404

def test_download_returns_404_when_not_completed():
    with patch("backend.routers.videos.db.get_video") as mock_get:
        mock_get.return_value = {"status": "processing", "video_path": None}
        resp = client.get("/videos/abc/download")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — expect failure**

```bash
python -m pytest backend/tests/test_videos_router.py -v
```

Expected: ImportError — main.py does not exist yet.

- [ ] **Step 3: Implement routers/videos.py**

Create `backend/routers/videos.py`:
```python
import os
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from redis import Redis
from rq import Queue

import backend.database as db
from backend.pipeline.runner import PipelineInput, run_pipeline

router = APIRouter()

_redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
_queue = Queue(connection=_redis)


class CreateVideoRequest(BaseModel):
    topic: str
    format: Literal["short", "long"]


@router.post("/")
def create_video(request: CreateVideoRequest):
    video_id = str(uuid4())
    db.create_video(video_id, request.topic, request.format)
    _queue.enqueue(
        run_pipeline,
        PipelineInput(topic=request.topic, format=request.format, job_id=video_id),
    )
    return {"id": video_id}


@router.get("/{video_id}/status")
def get_status(video_id: str):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{video_id}/download")
def download_video(video_id: str):
    video = db.get_video(video_id)
    if not video or video["status"] != "completed":
        raise HTTPException(status_code=404, detail="Video not ready")
    return FileResponse(
        video["video_path"],
        media_type="video/mp4",
        filename=f"{video_id}.mp4",
    )
```

- [ ] **Step 4: Implement main.py**

Create `backend/main.py`:
```python
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers.videos import router as videos_router

app = FastAPI(title="AI Video Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

app.include_router(videos_router, prefix="/videos")
```

- [ ] **Step 5: Implement worker.py**

Create `backend/worker.py`:
```python
import os
from dotenv import load_dotenv
load_dotenv()

from redis import Redis
from rq import Worker, Queue

if __name__ == "__main__":
    redis_conn = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    q = Queue(connection=redis_conn)
    worker = Worker([q], connection=redis_conn)
    worker.work()
```

- [ ] **Step 6: Run tests — expect pass**

```bash
python -m pytest backend/tests/test_videos_router.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 7: Commit**

```bash
git add backend/main.py backend/routers/videos.py backend/worker.py backend/tests/test_videos_router.py
git commit -m "feat: FastAPI routes, RQ worker, CORS"
```

---

## Task 9: Next.js Frontend

**Files:**
- Create: `frontend/` (Next.js app)
- Create: `frontend/next.config.js`
- Create: `frontend/app/page.tsx`
- Create: `frontend/components/GenerateForm.tsx`
- Create: `frontend/components/StatusPoller.tsx`

- [ ] **Step 1: Scaffold Next.js app**

```bash
cd ai-video-platform
npx create-next-app@14 frontend --typescript --app --no-tailwind --eslint --no-src-dir --import-alias "@/*"
```

When prompted, accept defaults.

- [ ] **Step 2: Configure API proxy in next.config.js**

Replace the contents of `frontend/next.config.js`:
```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/:path*',
      },
    ]
  },
}

module.exports = nextConfig
```

- [ ] **Step 3: Create GenerateForm component**

Create `frontend/components/GenerateForm.tsx`:
```tsx
'use client'
import { useState } from 'react'

interface Props {
  onCreated: (videoId: string) => void
}

export default function GenerateForm({ onCreated }: Props) {
  const [topic, setTopic] = useState('')
  const [format, setFormat] = useState<'short' | 'long'>('short')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/videos/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, format }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const { id } = await res.json()
      onCreated(id)
    } catch (err: any) {
      setError(err.message || 'Something went wrong. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label htmlFor="topic" style={{ display: 'block', marginBottom: 4 }}>
          Video Topic
        </label>
        <input
          id="topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="e.g. How to learn TypeScript in 2026"
          required
          style={{ width: '100%', padding: '8px 12px', fontSize: 16, boxSizing: 'border-box' }}
        />
      </div>

      <div>
        <label htmlFor="format" style={{ display: 'block', marginBottom: 4 }}>
          Format
        </label>
        <select
          id="format"
          value={format}
          onChange={(e) => setFormat(e.target.value as 'short' | 'long')}
          style={{ padding: '8px 12px', fontSize: 16 }}
        >
          <option value="short">Short — TikTok / Reels / Shorts (up to 60s)</option>
          <option value="long">Long — YouTube (3–15 min)</option>
        </select>
      </div>

      {error && <p style={{ color: '#c00', margin: 0 }}>{error}</p>}

      <button
        type="submit"
        disabled={loading || !topic.trim()}
        style={{ padding: '10px 24px', fontSize: 16, cursor: loading ? 'wait' : 'pointer' }}
      >
        {loading ? 'Starting generation...' : 'Generate Video'}
      </button>
    </form>
  )
}
```

- [ ] **Step 4: Create StatusPoller component**

Create `frontend/components/StatusPoller.tsx`:
```tsx
'use client'
import { useEffect, useState } from 'react'

interface VideoStatus {
  id: string
  topic: string
  format: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  video_path: string | null
  error: string | null
}

interface Props {
  videoId: string
  onReset: () => void
}

export default function StatusPoller({ videoId, onReset }: Props) {
  const [data, setData] = useState<VideoStatus | null>(null)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const res = await fetch(`/api/videos/${videoId}/status`)
        const json: VideoStatus = await res.json()
        if (!cancelled) setData(json)
        if (!cancelled && json.status !== 'completed' && json.status !== 'failed') {
          setTimeout(poll, 3000)
        }
      } catch {
        if (!cancelled) setTimeout(poll, 5000)
      }
    }
    poll()
    return () => { cancelled = true }
  }, [videoId])

  if (!data) return <p>Connecting...</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <p><strong>Topic:</strong> {data.topic}</p>
      <p><strong>Format:</strong> {data.format}</p>
      <p><strong>Status:</strong> {data.status}</p>

      {(data.status === 'pending' || data.status === 'processing') && (
        <p style={{ color: '#555' }}>Generating your video — this takes 1–5 minutes...</p>
      )}

      {data.status === 'completed' && (
        <div>
          <p style={{ color: 'green' }}>Your video is ready!</p>
          <a href={`/api/videos/${videoId}/download`} download>
            <button style={{ padding: '10px 24px', fontSize: 16 }}>Download MP4</button>
          </a>
        </div>
      )}

      {data.status === 'failed' && (
        <p style={{ color: '#c00' }}>Generation failed: {data.error}</p>
      )}

      <button
        onClick={onReset}
        style={{ padding: '8px 16px', marginTop: 8, cursor: 'pointer' }}
      >
        Generate Another Video
      </button>
    </div>
  )
}
```

- [ ] **Step 5: Replace app/page.tsx**

Replace the contents of `frontend/app/page.tsx`:
```tsx
'use client'
import { useState } from 'react'
import GenerateForm from '@/components/GenerateForm'
import StatusPoller from '@/components/StatusPoller'

export default function Home() {
  const [videoId, setVideoId] = useState<string | null>(null)

  return (
    <main style={{ maxWidth: 600, margin: '60px auto', padding: '0 24px', fontFamily: 'sans-serif' }}>
      <h1 style={{ marginBottom: 32 }}>AI Video Generator</h1>
      {videoId === null ? (
        <GenerateForm onCreated={setVideoId} />
      ) : (
        <StatusPoller videoId={videoId} onReset={() => setVideoId(null)} />
      )}
    </main>
  )
}
```

- [ ] **Step 6: Install frontend dependencies and verify build**

```bash
cd ai-video-platform/frontend
npm install
npm run build
```

Expected: build completes with no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
cd ai-video-platform
git add frontend/
git commit -m "feat: Next.js frontend with generation form and status polling"
```

---

## Task 10: End-to-End Local Test

- [ ] **Step 1: Start Redis (in a separate terminal)**

```bash
redis-server
```

Expected: Redis starts on port 6379.

- [ ] **Step 2: Start FastAPI (in a separate terminal)**

```bash
cd ai-video-platform
uvicorn backend.main:app --reload --port 8000
```

Expected: `Application startup complete` logged.

- [ ] **Step 3: Start RQ worker (in a separate terminal)**

```bash
cd ai-video-platform
python -m backend.worker
```

Expected: `Worker started` logged.

- [ ] **Step 4: Start Next.js (in a separate terminal)**

```bash
cd ai-video-platform/frontend
npm run dev
```

Expected: `Ready on http://localhost:3000`

- [ ] **Step 5: Test the happy path**

1. Open `http://localhost:3000`
2. Enter topic: `"How to stay focused while working from home"`
3. Select format: `Short`
4. Click **Generate Video**
5. Page switches to status view showing `pending` → `processing`
6. After 1–3 minutes, status changes to `completed`
7. Click **Download MP4**
8. Verify the file plays in a video player with voice-over and subtitles

- [ ] **Step 6: Test error handling**

1. Stop Redis (`Ctrl+C` the redis-server)
2. Try to generate a new video
3. Expect: FastAPI returns 500 or connection error shown in UI
4. Restart Redis and confirm it recovers

- [ ] **Step 7: Run full test suite**

```bash
cd ai-video-platform
python -m pytest backend/tests/ -v
```

Expected: all tests PASSED.

- [ ] **Step 8: Final commit**

```bash
git add .
git commit -m "feat: complete MVP — local AI video generation platform"
```

---

## Running the App (Quick Reference)

```bash
# Terminal 1
redis-server

# Terminal 2
cd ai-video-platform && uvicorn backend.main:app --reload --port 8000

# Terminal 3
cd ai-video-platform && python -m backend.worker

# Terminal 4
cd ai-video-platform/frontend && npm run dev
```

Open `http://localhost:3000`

---

## Environment Variables (.env)

```
OPENAI_API_KEY=sk-...        # required: OpenAI API key
PEXELS_API_KEY=...           # required: get free key at pexels.com/api
DB_PATH=db.sqlite3           # optional: SQLite file path
REDIS_URL=redis://localhost:6379  # optional: Redis connection URL
```
