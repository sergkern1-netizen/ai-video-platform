# Video Render Quality Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать генерируемые видео визуально и звуково качественными: сцены вместо одного зацикленного клипа, без искажения пропорций, с плавными переходами и karaoke-субтитрами, с темпом, заточенным под платформу (YouTube long vs TikTok/Shorts short).

**Architecture:** GPT возвращает структуру сценария со сценами (`Script.scenes: list[Scene]`) вместо плоского текста. `voice_synthesizer.py` дополнительно транскрибирует свежесгенерированное TTS-аудио через Whisper для точных таймингов по словам (с graceful fallback на оценку). `asset_fetcher.py` запрашивает у Pexels по одному ориентированному (portrait/landscape) клипу на каждую сцену с fallback на клип предыдущей сцены. `video_renderer.py` кадрирует каждый клип по центру под целевые пропорции (crop-to-fill), накладывает лёгкий Ken Burns zoom, склеивает сцены с crossfade, рисует word-by-word karaoke субтитры бандленным шрифтом, экспортирует с явным битрейтом.

**Tech Stack:** Python, MoviePy 1.0.3, Pillow 9.5.0, OpenAI SDK (TTS + Whisper), httpx (Pexels), pytest.

**Out of scope (отложено по решению пользователя):** фоновая музыка — спек описывает её, но без файлов треков от пользователя её не из чего собирать; не реализуется в этом плане.

---

## Перед началом

Рабочая директория для всех команд: `D:\Нова папка\ai-video-platform`.

Шрифт для субтитров уже подготовлен в этой сессии (DejaVu Sans Bold, открытая лицензия Bitstream Vera, безопасна для коммита в репозиторий):

```bash
ls backend/assets/fonts/DejaVuSans-Bold.ttf
```

Ожидаемый результат: файл существует (~704 KB). Если файла нет — взять `DejaVuSans-Bold.ttf` из пакета matplotlib (`site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf`) и скопировать в `backend/assets/fonts/`.

---

### Task 1: `Scene`/`Script` со сценами в `script_generator.py`

**Files:**
- Modify: `backend/pipeline/script_generator.py` (полная замена содержимого)
- Test: `backend/tests/test_script_generator.py` (полная замена содержимого)

- [ ] **Step 1: Заменить тесты на новый контракт (сцены вместо плоского текста)**

Полностью заменить содержимое `backend/tests/test_script_generator.py`:

```python
import json
from unittest.mock import patch, MagicMock
from backend.pipeline.script_generator import generate_script, Script, Scene

def _mock_openai(content: str):
    mock = MagicMock()
    mock.choices[0].message.content = content
    return mock

def test_generate_script_short_returns_script_dataclass():
    payload = json.dumps({
        "title": "How to Learn Python Fast",
        "mood": "upbeat",
        "scenes": [
            {
                "text": "Python is one of the most popular programming languages today.",
                "keywords": ["python", "code"],
                "duration_sec": 5,
            },
        ],
        "duration_sec": 50,
    })
    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_openai(payload)
        script = generate_script("How to learn Python", "short")

    assert isinstance(script, Script)
    assert script.title == "How to Learn Python Fast"
    assert script.mood == "upbeat"
    assert len(script.scenes) == 1
    assert isinstance(script.scenes[0], Scene)
    assert script.scenes[0].keywords == ["python", "code"]
    assert "Python" in script.body
    assert script.duration_sec == 50

def test_generate_script_long_requests_600_seconds():
    payload = json.dumps({
        "title": "The Full History of Rome",
        "mood": "dramatic",
        "scenes": [
            {"text": "Rome was not built in a day.", "keywords": ["rome", "history"], "duration_sec": 10},
        ],
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
        "mood": "calm",
        "scenes": [{"text": "Body text here.", "keywords": ["retry"], "duration_sec": 5}],
        "duration_sec": 50,
    })
    good_response = _mock_openai(good_payload)

    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = [
            bad_response, good_response
        ]
        script = generate_script("test topic", "short")

    assert script.title == "Retry Works"

def test_generate_script_defaults_mood_when_missing():
    payload = json.dumps({
        "title": "No Mood Field",
        "scenes": [{"text": "Some text.", "keywords": ["x"], "duration_sec": 5}],
        "duration_sec": 50,
    })
    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_openai(payload)
        script = generate_script("topic", "short")

    assert script.mood == "corporate"

def test_generate_script_body_joins_scene_texts():
    payload = json.dumps({
        "title": "Multi Scene",
        "mood": "calm",
        "scenes": [
            {"text": "First scene text.", "keywords": ["a"], "duration_sec": 4},
            {"text": "Second scene text.", "keywords": ["b"], "duration_sec": 4},
        ],
        "duration_sec": 8,
    })
    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_openai(payload)
        script = generate_script("topic", "short")

    assert script.body == "First scene text. Second scene text."
```

- [ ] **Step 2: Запустить тесты, убедиться что падают (модуль ещё не обновлён)**

Run: `pytest backend/tests/test_script_generator.py -v`
Expected: FAIL (ImportError: cannot import name 'Scene', либо AttributeError на `script.mood`/`script.scenes`).

- [ ] **Step 3: Переписать `backend/pipeline/script_generator.py`**

Полностью заменить содержимое файла:

```python
import json
import os
from dataclasses import dataclass
from openai import OpenAI

@dataclass
class Scene:
    text: str
    keywords: list[str]
    duration_sec: int

@dataclass
class Script:
    title: str
    scenes: list[Scene]
    body: str
    mood: str
    duration_sec: int

_SHORT_PROMPT = """Write a YouTube Shorts / TikTok video script about: "{topic}"

Format: vertical short video, under 60 seconds
Target: ~120 words total, broken into scenes

Rules:
- The FIRST scene must be a strong attention-grabbing hook (1-2 sentences) that makes viewers want to keep watching.
- Each scene should be 3-5 seconds long and represent one visual beat / idea.
- Keep pacing fast and energetic.

Respond with JSON only — no markdown, no explanation:
{{
  "title": "video title (max 60 chars)",
  "mood": "one of: upbeat, calm, dramatic, corporate",
  "scenes": [
    {{"text": "narration text for this scene", "keywords": ["visual1", "visual2"], "duration_sec": 4}}
  ],
  "duration_sec": 50
}}"""

_LONG_PROMPT = """Write a YouTube video script about: "{topic}"

Format: horizontal YouTube video, 10 minutes
Target: ~1500 words total, broken into scenes

Rules:
- Start with a calm, welcoming introduction scene (not an abrupt hook).
- Each scene should be 8-15 seconds long and cover one sub-topic or idea.
- Keep a steady, explanatory pace suitable for long-form viewing.

Respond with JSON only — no markdown, no explanation:
{{
  "title": "video title (max 70 chars)",
  "mood": "one of: upbeat, calm, dramatic, corporate",
  "scenes": [
    {{"text": "narration text for this scene", "keywords": ["visual1", "visual2"], "duration_sec": 10}}
  ],
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
            scenes = [
                Scene(
                    text=s["text"],
                    keywords=s["keywords"],
                    duration_sec=s["duration_sec"],
                )
                for s in data["scenes"]
            ]
            body = " ".join(scene.text for scene in scenes)
            return Script(
                title=data["title"],
                scenes=scenes,
                body=body,
                mood=data.get("mood", "corporate"),
                duration_sec=data["duration_sec"],
            )
        except (json.JSONDecodeError, KeyError):
            if attempt == max_retries - 1:
                raise ValueError(f"Script generator failed after {max_retries} attempts. Last response: {raw[:200]}")
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `pytest backend/tests/test_script_generator.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/script_generator.py backend/tests/test_script_generator.py
git commit -m "feat: scene-based script generation with mood and format-aware pacing"
```

---

### Task 2: Реальные тайминги слов через Whisper в `voice_synthesizer.py`

**Files:**
- Modify: `backend/pipeline/voice_synthesizer.py` (полная замена содержимого)
- Test: `backend/tests/test_voice_synthesizer.py` (добавить новый тест, остальные не трогать)

- [ ] **Step 1: Добавить тест успешной Whisper-транскрипции**

В конец `backend/tests/test_voice_synthesizer.py` добавить:

```python
def test_synthesize_voice_uses_whisper_word_timings(tmp_path):
    audio_path = tmp_path / "job-789.mp3"
    audio_path.write_bytes(b"fake audio data")

    mock_response = MagicMock()
    mock_response.stream_to_file = MagicMock()
    mock_transcript = MagicMock()
    mock_transcript.words = [
        {"word": "Hello", "start": 0.0, "end": 0.4},
        {"word": "world", "start": 0.4, "end": 0.9},
    ]

    with patch("backend.pipeline.voice_synthesizer.OpenAI") as MockClient, \
         patch("backend.pipeline.voice_synthesizer.AudioFileClip") as MockAudio:
        MockClient.return_value.audio.speech.create.return_value = mock_response
        MockClient.return_value.audio.transcriptions.create.return_value = mock_transcript
        MockAudio.return_value.duration = 1.0
        MockAudio.return_value.close = MagicMock()

        result = synthesize_voice(_make_script("Hello world"), "job-789", audio_dir=str(tmp_path))

    assert result.word_timings == [
        {"text": "Hello", "start": 0.0, "end": 0.4},
        {"text": "world", "start": 0.4, "end": 0.9},
    ]

def test_synthesize_voice_falls_back_to_estimate_when_whisper_fails(tmp_path):
    mock_response = MagicMock()
    mock_response.stream_to_file = MagicMock()

    with patch("backend.pipeline.voice_synthesizer.OpenAI") as MockClient, \
         patch("backend.pipeline.voice_synthesizer.AudioFileClip") as MockAudio:
        MockClient.return_value.audio.speech.create.return_value = mock_response
        MockClient.return_value.audio.transcriptions.create.side_effect = Exception("network error")
        MockAudio.return_value.duration = 2.0
        MockAudio.return_value.close = MagicMock()

        result = synthesize_voice(_make_script("one two"), "job-999", audio_dir=str(tmp_path))

    assert result.word_timings == [
        {"text": "one", "start": 0.0, "end": 1.0},
        {"text": "two", "start": 1.0, "end": 2.0},
    ]
```

(Заметка: `audio_path.write_bytes(...)` нужен потому что `synthesize_voice` теперь открывает этот файл для отправки в Whisper — без реального файла на диске открытие упадёт ещё до вызова API, и тест случайно проверит fallback-путь вместо success-пути. Для теста fallback (`test_synthesize_voice_falls_back_...`) файл специально НЕ создаётся: `open()` упадёт с `FileNotFoundError`, что само по себе провоцирует тот же fallback, а к нему добавляется явный `side_effect=Exception` на самом API-вызове как дополнительная гарантия — итог одинаков в обоих случаях.)

- [ ] **Step 2: Запустить тесты, убедиться что новые падают**

Run: `pytest backend/tests/test_voice_synthesizer.py -v`
Expected: FAIL на двух новых тестах (текущая `_estimate_timings` группирует по 8 слов, а не по одному, и Whisper вообще не вызывается).

- [ ] **Step 3: Переписать `backend/pipeline/voice_synthesizer.py`**

Полностью заменить содержимое файла:

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

    word_timings = _whisper_word_timings(client, audio_path)
    if word_timings is None:
        word_timings = _estimate_timings(script.body, duration)

    return VoiceOutput(audio_path=audio_path, word_timings=word_timings)

def _whisper_word_timings(client: OpenAI, audio_path: str) -> list[dict] | None:
    try:
        with open(audio_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        return [
            {"text": w["word"], "start": w["start"], "end": w["end"]}
            for w in transcript.words
        ]
    except Exception:
        return None

def _estimate_timings(text: str, total_duration: float) -> list[dict]:
    words = text.split()
    if not words:
        return []
    time_per_word = total_duration / len(words)
    return [
        {
            "text": word,
            "start": round(i * time_per_word, 2),
            "end": round((i + 1) * time_per_word, 2),
        }
        for i, word in enumerate(words)
    ]
```

- [ ] **Step 4: Запустить тесты, убедиться что все проходят**

Run: `pytest backend/tests/test_voice_synthesizer.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/voice_synthesizer.py backend/tests/test_voice_synthesizer.py
git commit -m "feat: real per-word timings via Whisper transcription with fallback"
```

---

### Task 3: По одному ориентированному клипу на сцену в `asset_fetcher.py`

**Files:**
- Modify: `backend/pipeline/asset_fetcher.py` (полная замена содержимого)
- Test: `backend/tests/test_asset_fetcher.py` (полная замена содержимого)

- [ ] **Step 1: Заменить тесты на новый контракт (сцены + ориентация + fallback)**

Полностью заменить содержимое `backend/tests/test_asset_fetcher.py`:

```python
from unittest.mock import patch, MagicMock
from backend.pipeline.script_generator import Scene
from backend.pipeline.asset_fetcher import fetch_assets, Assets

def _scene(keywords=None, duration_sec=5):
    return Scene(text="test scene", keywords=keywords or ["nature"], duration_sec=duration_sec)

def _mock_pexels_response(videos: list):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"videos": videos}
    return mock

def test_fetch_assets_returns_none_clips_when_pexels_empty():
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get:
        mock_get.return_value = _mock_pexels_response([])
        assets = fetch_assets([_scene()], "short")
    assert isinstance(assets, Assets)
    assert assets.video_clips == [None]

def test_fetch_assets_returns_none_on_http_error():
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get:
        mock_get.side_effect = Exception("connection refused")
        assets = fetch_assets([_scene()], "short")
    assert assets.video_clips == [None]

def test_fetch_assets_returns_clip_on_success(tmp_path):
    mock_video = {
        "id": 999,
        "duration": 15,
        "video_files": [
            {"width": 1920, "height": 1080, "link": "https://example.com/clip.mp4"}
        ],
    }
    with patch("backend.pipeline.asset_fetcher.httpx.get") as mock_get, \
         patch("backend.pipeline.asset_fetcher._download_clip") as mock_dl:
        mock_get.return_value = _mock_pexels_response([mock_video])
        assets = fetch_assets([_scene()], "short", clip_dir=str(tmp_path))

    assert len(assets.video_clips) == 1
    assert assets.video_clips[0]["duration_sec"] == 15
    mock_dl.assert_called_once()

def test_fetch_assets_uses_portrait_orientation_for_short():
    captured = {}
    def capture(*args, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return _mock_pexels_response([])
    with patch("backend.pipeline.asset_fetcher.httpx.get", side_effect=capture):
        fetch_assets([_scene()], "short")
    assert captured["params"]["orientation"] == "portrait"

def test_fetch_assets_uses_landscape_orientation_for_long():
    captured = {}
    def capture(*args, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return _mock_pexels_response([])
    with patch("backend.pipeline.asset_fetcher.httpx.get", side_effect=capture):
        fetch_assets([_scene()], "long")
    assert captured["params"]["orientation"] == "landscape"

def test_fetch_assets_falls_back_to_previous_scene_clip():
    mock_video = {
        "id": 1,
        "duration": 10,
        "video_files": [{"width": 1920, "height": 1080, "link": "https://example.com/clip.mp4"}],
    }
    responses = [_mock_pexels_response([mock_video]), _mock_pexels_response([])]
    with patch("backend.pipeline.asset_fetcher.httpx.get", side_effect=responses), \
         patch("backend.pipeline.asset_fetcher._download_clip"):
        assets = fetch_assets([_scene(), _scene()], "short", clip_dir="temp")

    assert assets.video_clips[0] is not None
    assert assets.video_clips[1] == assets.video_clips[0]

def test_fetch_assets_first_scene_with_no_result_stays_none():
    responses = [_mock_pexels_response([])]
    with patch("backend.pipeline.asset_fetcher.httpx.get", side_effect=responses):
        assets = fetch_assets([_scene()], "short")

    assert assets.video_clips == [None]
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `pytest backend/tests/test_asset_fetcher.py -v`
Expected: FAIL (текущая `fetch_assets(keywords, duration_sec)` принимает другую сигнатуру).

- [ ] **Step 3: Переписать `backend/pipeline/asset_fetcher.py`**

Полностью заменить содержимое файла:

```python
import os
from dataclasses import dataclass, field
from typing import Literal
import httpx
from backend.pipeline.script_generator import Scene

PEXELS_API_URL = "https://api.pexels.com/videos/search"

_ORIENTATION_BY_FORMAT = {"short": "portrait", "long": "landscape"}

@dataclass
class Assets:
    video_clips: list = field(default_factory=list)  # list[dict | None], aligned with scenes

def fetch_assets(scenes: list[Scene], format: Literal["short", "long"], clip_dir: str = "temp") -> Assets:
    orientation = _ORIENTATION_BY_FORMAT.get(format, "landscape")
    clips = []
    last_successful = None

    for scene in scenes:
        clip = _fetch_scene_clip(scene, orientation, clip_dir)
        if clip is None:
            clip = last_successful
        else:
            last_successful = clip
        clips.append(clip)

    return Assets(video_clips=clips)

def _fetch_scene_clip(scene: Scene, orientation: str, clip_dir: str):
    query = " ".join(scene.keywords[:2])
    try:
        resp = httpx.get(
            PEXELS_API_URL,
            headers={"Authorization": os.environ["PEXELS_API_KEY"]},
            params={"query": query, "per_page": 5, "min_duration": 5, "orientation": orientation},
            timeout=15,
        )
        videos = resp.json().get("videos", [])
    except Exception:
        return None

    if not videos:
        return None

    os.makedirs(clip_dir, exist_ok=True)
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
            return {"path": clip_path, "duration_sec": video["duration"]}
        except Exception:
            continue

    return None

def _download_clip(url: str, path: str) -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            with open(path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
```

- [ ] **Step 4: Запустить тесты, убедиться что все проходят**

Run: `pytest backend/tests/test_asset_fetcher.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/asset_fetcher.py backend/tests/test_asset_fetcher.py
git commit -m "feat: per-scene orientation-aware Pexels fetching with fallback"
```

---

### Task 4: Шрифт для субтитров в репозитории

**Files:**
- Create: `backend/assets/fonts/DejaVuSans-Bold.ttf` (бинарный файл, уже скопирован в этой сессии)

- [ ] **Step 1: Проверить, что шрифт на месте**

Run: `ls -la backend/assets/fonts/DejaVuSans-Bold.ttf`
Expected: файл существует, размер ~704128 байт.

Если файла нет (например, план выполняется в чистом воркчтри без этого файла) — скопировать его из matplotlib:

```bash
pip install matplotlib --quiet
python -c "
import matplotlib, os, shutil
src = os.path.join(os.path.dirname(matplotlib.__file__), 'mpl-data', 'fonts', 'ttf', 'DejaVuSans-Bold.ttf')
os.makedirs('backend/assets/fonts', exist_ok=True)
shutil.copy(src, 'backend/assets/fonts/DejaVuSans-Bold.ttf')
"
pip uninstall matplotlib -y --quiet
```

- [ ] **Step 2: Commit**

```bash
git add backend/assets/fonts/DejaVuSans-Bold.ttf
git commit -m "chore: bundle DejaVu Sans Bold font for subtitle rendering"
```

---

### Task 5: Crop-to-fill, Ken Burns, crossfade и karaoke-субтитры в `video_renderer.py`

**Files:**
- Modify: `backend/pipeline/video_renderer.py` (полная замена содержимого)
- Test: `backend/tests/test_video_renderer.py` (полная замена содержимого)

- [ ] **Step 1: Заменить тесты на новый контракт**

Полностью заменить содержимое `backend/tests/test_video_renderer.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from moviepy.editor import ColorClip
from backend.pipeline.script_generator import Script, Scene
from backend.pipeline.voice_synthesizer import VoiceOutput
from backend.pipeline.asset_fetcher import Assets
from backend.pipeline.video_renderer import (
    render_video,
    _crop_to_fill,
    _ken_burns_zoom_factor,
    _group_words_into_windows,
)

def _make_inputs(clips=None, scenes=None):
    scenes = scenes or [Scene(text="Scene one text", keywords=["test"], duration_sec=5)]
    script = Script(
        title="Test Video",
        scenes=scenes,
        body=" ".join(s.text for s in scenes),
        mood="calm",
        duration_sec=sum(s.duration_sec for s in scenes),
    )
    voice = VoiceOutput(
        audio_path="temp/test.mp3",
        word_timings=[
            {"text": "This", "start": 0.0, "end": 0.3},
            {"text": "is", "start": 0.3, "end": 0.5},
        ],
    )
    if clips is None:
        clips = [None] * len(scenes)
    assets = Assets(video_clips=clips)
    return script, voice, assets

def test_render_video_uses_color_clip_when_no_clips_available(tmp_path):
    script, voice, assets = _make_inputs(clips=[None])
    output_path = str(tmp_path / "out.mp4")

    with patch("backend.pipeline.video_renderer.AudioFileClip") as MockAudio, \
         patch("backend.pipeline.video_renderer.ColorClip") as MockColor, \
         patch("backend.pipeline.video_renderer.CompositeVideoClip") as MockComposite, \
         patch("backend.pipeline.video_renderer._make_karaoke_clips") as MockKaraoke:
        MockAudio.return_value.duration = 5.0
        MockColor.return_value.duration = 5.0
        MockComposite.return_value.set_audio.return_value = MagicMock()
        MockComposite.return_value.set_audio.return_value.write_videofile = MagicMock()
        MockKaraoke.return_value = []

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
         patch("backend.pipeline.video_renderer._make_karaoke_clips") as MockKaraoke, \
         patch("backend.pipeline.video_renderer._crop_to_fill") as MockCrop, \
         patch("backend.pipeline.video_renderer._apply_ken_burns") as MockKenBurns:
        MockAudio.return_value.duration = 5.0
        mock_clip = MagicMock()
        mock_clip.duration = 15.0
        mock_clip.subclip.return_value = mock_clip
        mock_clip.loop.return_value = mock_clip
        MockVFC.return_value = mock_clip
        MockCrop.return_value = mock_clip
        MockKenBurns.return_value = mock_clip
        MockComposite.return_value.set_audio.return_value = MagicMock()
        MockComposite.return_value.set_audio.return_value.write_videofile = MagicMock()
        MockKaraoke.return_value = []

        render_video(script, voice, assets, "short", output_path)

    MockColor.assert_not_called()
    MockVFC.assert_called_once_with("temp/clip1.mp4")

def test_render_video_concatenates_multiple_scenes_with_crossfade(tmp_path):
    scenes = [
        Scene(text="Scene one", keywords=["a"], duration_sec=3),
        Scene(text="Scene two", keywords=["b"], duration_sec=3),
    ]
    script, voice, assets = _make_inputs(
        clips=[
            {"path": "temp/clip1.mp4", "duration_sec": 10},
            {"path": "temp/clip2.mp4", "duration_sec": 10},
        ],
        scenes=scenes,
    )
    output_path = str(tmp_path / "out.mp4")

    with patch("backend.pipeline.video_renderer.AudioFileClip") as MockAudio, \
         patch("backend.pipeline.video_renderer.VideoFileClip") as MockVFC, \
         patch("backend.pipeline.video_renderer.CompositeVideoClip") as MockComposite, \
         patch("backend.pipeline.video_renderer._make_karaoke_clips") as MockKaraoke, \
         patch("backend.pipeline.video_renderer._crop_to_fill") as MockCrop, \
         patch("backend.pipeline.video_renderer._apply_ken_burns") as MockKenBurns, \
         patch("backend.pipeline.video_renderer.concatenate_videoclips") as MockConcat:
        MockAudio.return_value.duration = 6.0
        mock_clip = MagicMock()
        mock_clip.duration = 10.0
        mock_clip.subclip.return_value = mock_clip
        mock_clip.loop.return_value = mock_clip
        mock_clip.crossfadein.return_value = mock_clip
        MockVFC.return_value = mock_clip
        MockCrop.return_value = mock_clip
        MockKenBurns.return_value = mock_clip
        MockConcat.return_value = mock_clip
        MockComposite.return_value.set_audio.return_value = MagicMock()
        MockComposite.return_value.set_audio.return_value.write_videofile = MagicMock()
        MockKaraoke.return_value = []

        render_video(script, voice, assets, "short", output_path)

    MockConcat.assert_called_once()

def test_ken_burns_zoom_factor_at_start_is_one():
    assert _ken_burns_zoom_factor(0.0, 10.0) == 1.0

def test_ken_burns_zoom_factor_at_end_is_max():
    assert _ken_burns_zoom_factor(10.0, 10.0) == pytest.approx(1.08)

def test_ken_burns_zoom_factor_clamps_beyond_duration():
    assert _ken_burns_zoom_factor(20.0, 10.0) == pytest.approx(1.08)

def test_ken_burns_zoom_factor_zero_duration_returns_one():
    assert _ken_burns_zoom_factor(5.0, 0.0) == 1.0

def test_crop_to_fill_produces_target_size():
    clip = ColorClip(size=(1920, 1080), color=[10, 10, 10], duration=1)
    cropped = _crop_to_fill(clip, (1080, 1920))
    assert cropped.size == (1080, 1920)

def test_crop_to_fill_keeps_size_when_already_matching():
    clip = ColorClip(size=(1080, 1920), color=[10, 10, 10], duration=1)
    cropped = _crop_to_fill(clip, (1080, 1920))
    assert cropped.size == (1080, 1920)

def test_group_words_into_windows_splits_by_window_size():
    words = [{"text": str(i), "start": i, "end": i + 1} for i in range(14)]
    windows = _group_words_into_windows(words, window_size=6)
    assert len(windows) == 3
    assert len(windows[0]) == 6
    assert len(windows[2]) == 2

def test_group_words_into_windows_empty_input():
    assert _group_words_into_windows([], window_size=6) == []
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `pytest backend/tests/test_video_renderer.py -v`
Expected: FAIL (ImportError: `_crop_to_fill`, `_ken_burns_zoom_factor`, `_group_words_into_windows` ещё не существуют; `Script`/`Scene` сигнатуры изменились).

- [ ] **Step 3: Переписать `backend/pipeline/video_renderer.py`**

Полностью заменить содержимое файла:

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
    concatenate_videoclips,
)
from backend.pipeline.script_generator import Script
from backend.pipeline.voice_synthesizer import VoiceOutput
from backend.pipeline.asset_fetcher import Assets

_SIZES = {
    "short": (1080, 1920),
    "long": (1920, 1080),
}
_BITRATES = {
    "short": "8000k",
    "long": "6000k",
}
_CROSSFADE_SEC = 0.4
_KEN_BURNS_ZOOM = 1.08
_KARAOKE_WINDOW = 6
_FONT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "assets", "fonts", "DejaVuSans-Bold.ttf"
)
_BG_COLOR = [20, 20, 40]


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

    background = _build_background(script, assets, size, duration)
    subtitle_clips = _make_karaoke_clips(voice.word_timings, size)

    final = CompositeVideoClip([background] + subtitle_clips, size=size)
    final = final.set_audio(audio)
    final.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        bitrate=_BITRATES[format],
        logger=None,
    )


def _build_background(script: Script, assets: Assets, size: tuple, duration: float):
    if not assets.video_clips or all(c is None for c in assets.video_clips):
        return ColorClip(size=size, color=_BG_COLOR, duration=duration)

    total_planned = sum(s.duration_sec for s in script.scenes) or duration
    scale = duration / total_planned

    scene_clips = []
    for scene, clip_info in zip(script.scenes, assets.video_clips):
        scene_duration = scene.duration_sec * scale
        if clip_info is None:
            scene_clip = ColorClip(size=size, color=_BG_COLOR, duration=scene_duration)
        else:
            scene_clip = _prepare_scene_clip(clip_info["path"], size, scene_duration)
        scene_clips.append(scene_clip)

    return _concatenate_with_crossfade(scene_clips)


def _prepare_scene_clip(clip_path: str, size: tuple, duration: float):
    clip = VideoFileClip(clip_path)
    if clip.duration < duration:
        clip = clip.loop(duration=duration)
    else:
        clip = clip.subclip(0, duration)
    clip = _crop_to_fill(clip, size)
    clip = _apply_ken_burns(clip, size)
    return clip


def _crop_to_fill(clip, size: tuple):
    target_w, target_h = size
    target_ratio = target_w / target_h
    clip_ratio = clip.w / clip.h

    if clip_ratio > target_ratio:
        new_w = int(clip.h * target_ratio)
        x1 = (clip.w - new_w) // 2
        cropped = clip.crop(x1=x1, x2=x1 + new_w, y1=0, y2=clip.h)
    elif clip_ratio < target_ratio:
        new_h = int(clip.w / target_ratio)
        y1 = (clip.h - new_h) // 2
        cropped = clip.crop(x1=0, x2=clip.w, y1=y1, y2=y1 + new_h)
    else:
        cropped = clip

    return cropped.resize(size)


def _ken_burns_zoom_factor(t: float, duration: float, max_zoom: float = _KEN_BURNS_ZOOM) -> float:
    if duration <= 0:
        return 1.0
    progress = min(max(t / duration, 0.0), 1.0)
    return 1 + (max_zoom - 1) * progress


def _apply_ken_burns(clip, size: tuple):
    w, h = size
    duration = clip.duration

    def _center_crop(frame):
        fh, fw = frame.shape[0], frame.shape[1]
        x0 = max((fw - w) // 2, 0)
        y0 = max((fh - h) // 2, 0)
        return frame[y0 : y0 + h, x0 : x0 + w]

    zoomed = clip.resize(lambda t: _ken_burns_zoom_factor(t, duration))
    return zoomed.fl_image(_center_crop)


def _concatenate_with_crossfade(clips: list):
    if len(clips) == 1:
        return clips[0]

    faded = [clips[0]]
    for clip in clips[1:]:
        faded.append(clip.crossfadein(_CROSSFADE_SEC))

    return concatenate_videoclips(faded, padding=-_CROSSFADE_SEC, method="compose")


def _group_words_into_windows(word_timings: list, window_size: int = _KARAOKE_WINDOW) -> list:
    return [
        word_timings[i : i + window_size]
        for i in range(0, len(word_timings), window_size)
    ]


def _make_karaoke_clips(word_timings: list, size: tuple) -> list:
    clips = []
    for window in _group_words_into_windows(word_timings):
        for index, word in enumerate(window):
            clip_duration = word["end"] - word["start"]
            if clip_duration <= 0:
                continue
            img = _render_karaoke_frame(window, index, size)
            clip = ImageClip(np.array(img), duration=clip_duration).set_start(word["start"])
            clips.append(clip)
    return clips


def _render_karaoke_frame(window: list, active_index: int, size: tuple) -> Image.Image:
    w, h = size
    font_size = 64 if w == 1080 else 46
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(_FONT_PATH, font_size)

    words = [entry["text"] for entry in window]
    spacing = 14
    max_width = w - 80

    lines = [[]]
    line_width = 0
    for idx, word in enumerate(words):
        bbox = draw.textbbox((0, 0), word, font=font)
        word_w = bbox[2] - bbox[0]
        if line_width + word_w + spacing > max_width and lines[-1]:
            lines.append([])
            line_width = 0
        lines[-1].append(idx)
        line_width += word_w + spacing

    line_height = font_size + 16
    y = h - len(lines) * line_height - 80

    for line in lines:
        widths = []
        total_w = 0
        for idx in line:
            bbox = draw.textbbox((0, 0), words[idx], font=font)
            word_w = bbox[2] - bbox[0]
            widths.append(word_w)
            total_w += word_w + spacing
        total_w -= spacing

        x = (w - total_w) // 2
        for idx, word_w in zip(line, widths):
            color = (255, 215, 0, 255) if idx == active_index else (255, 255, 255, 255)
            draw.text((x + 2, y + 2), words[idx], fill=(0, 0, 0, 200), font=font)
            draw.text((x, y), words[idx], fill=color, font=font)
            x += word_w + spacing
        y += line_height

    return img
```

- [ ] **Step 4: Запустить тесты, убедиться что все проходят**

Run: `pytest backend/tests/test_video_renderer.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/video_renderer.py backend/tests/test_video_renderer.py
git commit -m "feat: crop-to-fill, Ken Burns zoom, crossfade transitions and karaoke subtitles"
```

---

### Task 6: Прокинуть сцены и формат в `runner.py`

**Files:**
- Modify: `backend/pipeline/runner.py:27-29`

- [ ] **Step 1: Изменить вызов `fetch_assets`**

В файле `backend/pipeline/runner.py` заменить:

```python
            assets_future = executor.submit(
                fetch_assets, script.keywords, script.duration_sec
            )
```

на:

```python
            assets_future = executor.submit(
                fetch_assets, script.scenes, pipeline_input.format
            )
```

- [ ] **Step 2: Проверить, что модуль импортируется без ошибок**

Run: `python -c "from backend.pipeline.runner import run_pipeline; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Запустить весь юнит-тестовый набор backend**

Run: `pytest backend/tests/ -v`
Expected: PASS (все тесты во всех файлах, включая `test_database.py` и `test_videos_router.py`, которые не менялись).

- [ ] **Step 4: Commit**

```bash
git add backend/pipeline/runner.py
git commit -m "feat: pass scenes and format to asset fetcher in pipeline runner"
```

---

### Task 7: Ручной E2E-тест на сайте

**Files:** нет изменений кода — только проверка работающей системы.

- [ ] **Step 1: Перезапустить RQ worker и uvicorn, чтобы подхватить весь новый код**

В двух отдельных терминалах (или через фоновые задачи харнеса):

```bash
cd "D:\Нова папка\ai-video-platform" && python -m backend.worker
```

```bash
cd "D:\Нова папка\ai-video-platform" && uvicorn backend.main:app --reload --port 8000
```

(Если процессы уже запущены с предыдущей сессии — остановить их и запустить заново: `uvicorn --reload` на этой машине не всегда надёжно подхватывает изменения через WatchFiles, см. `docs/session-history.md` Сессия 4.)

- [ ] **Step 2: Убедиться, что frontend и Redis тоже работают**

Redis — служба Memurai, должна слушать порт 6379 (`netstat -ano | grep 6379`). Frontend:

```bash
cd "D:\Нова папка\ai-video-platform\frontend" && npm run dev
```

Должен встать на порт 3000 (если порт занят посторонним процессом — освободить его, иначе сработает старая проблема с CORS, см. `docs/session-history.md` Сессия 4).

- [ ] **Step 3: Создать тестовое видео через API и дождаться завершения**

```bash
curl -s -X POST http://localhost:8000/videos/ -H "Origin: http://localhost:3000" -H "Content-Type: application/json" -d '{"topic":"5 простых утренних привычек","format":"short"}'
```

Скопировать `id` из ответа, затем опрашивать статус (использовать Monitor/`until`-цикл, не `sleep` вручную):

```bash
until status=$(curl -s http://localhost:8000/videos/<ID>/status); echo "$status" | grep -q '"status":"completed"\|"status":"failed"'; do sleep 5; done; echo "$status"
```

Expected: `"status":"completed"`, `video_path` указывает на файл в `output/`.

- [ ] **Step 4: Визуально проверить результат**

Открыть получившийся `output/<id>.mp4` (через `start output/<id>.mp4` или проводник) и убедиться:
- видео не искажено (пропорции 9:16 для short сохранены, картинка не сплющена/растянута);
- видно более одной сцены/клипа за ролик, со сменой по crossfade;
- субтитры идут word-by-word с подсветкой текущего слова, текст не "битый" (шрифт корректный);
- лёгкое плавное движение (zoom) на фоне, не статичная картинка.

- [ ] **Step 5: Повторить тест с `"format":"long"`**

```bash
curl -s -X POST http://localhost:8000/videos/ -H "Origin: http://localhost:3000" -H "Content-Type: application/json" -d '{"topic":"история древнего рима","format":"long"}'
```

Тот же цикл ожидания и визуальная проверка — пропорции 16:9, более длинные/спокойные сцены.

- [ ] **Step 6: Протестировать через браузер**

Открыть `http://localhost:3000`, заполнить форму, отправить, дождаться `StatusPoller` и убедиться, что UI корректно показывает завершение и ссылку на скачивание.

- [ ] **Step 7: Обновить `docs/session-history.md`**

Добавить запись о результатах E2E-теста новой версии рендерера (что проверено, что подтверждено визуально, остались ли замечания). Музыка — отметить как осознанно отложенную (нет источника треков).

---

## Self-review (выполнено при написании плана)

- **Покрытие спека:** сцены/scene-aware GPT — Task 1; реальные тайминги слов — Task 2; orientation-aware Pexels + fallback — Task 3; шрифт — Task 4; crop-to-fill/Ken Burns/crossfade/karaoke/битрейт — Task 5; интеграция в runner — Task 6; ручная проверка — Task 7. Фоновая музыка из спека явно вынесена в "Out of scope" по решению пользователя (нет источника треков).
- **Заглушки:** не найдено — весь код в шагах полный и рабочий, проверен smoke-тестом на реальных объектах MoviePy перед записью в план.
- **Согласованность типов:** `Scene`/`Script` определены в Task 1 и используются с одинаковыми полями (`text`, `keywords`, `duration_sec`) в Task 3 (`asset_fetcher`) и Task 5 (`video_renderer`); `Assets.video_clips` — список `dict | None`, выровненный по индексу со `scenes`, используется одинаково в Task 3 и Task 5.
