# Iterative Script Growth for Long-Format Videos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `generate_script(topic, "long")` reliably reach ~1500 words / 45+ scenes by issuing follow-up "continuation" calls to GPT when the first response falls short, instead of relying on a single call that systematically under-delivers.

**Architecture:** `backend/pipeline/script_generator.py` gains a continuation loop that runs only for `format == "long"`: after the first valid script is parsed, if its word count is below 90% of the 1500-word target, the code appends the first response to the chat history and asks for more *new* scenes, repeating up to 3 times. Each continuation response is parsed with its own bounded retry-on-invalid-JSON (reusing the existing retry pattern); if a continuation never produces valid JSON after its retries, the loop stops and returns whatever has accumulated so far — it never raises for this reason. `format == "short"` behavior is completely unchanged.

**Tech Stack:** Python, `openai` SDK (mocked in tests), pytest.

**Spec:** `docs/superpowers/specs/2026-06-18-long-script-length-design.md`

---

### Task 1: Continuation loop in `script_generator.py`

**Files:**
- Modify: `ai-video-platform/backend/pipeline/script_generator.py`
- Modify: `ai-video-platform/backend/tests/test_script_generator.py`

This is one cohesive change — the helper functions and the loop only make sense together. Follow TDD: update/add all the tests first, confirm the new/changed ones fail against the current implementation, then implement, then confirm everything passes.

- [ ] **Step 1: Update the existing long-format test so it reflects the new single-call-when-already-long-enough behavior**

The current `test_generate_script_long_requests_600_seconds` test uses a short (~7-word) mock scene. Once the continuation loop exists, a response that short would trigger continuations, and the test's `captured["messages"]` would end up holding the *last* call's messages instead of the first — breaking its original intent (checking the long-format prompt asks for 600 seconds). Fix this by making the mocked scene long enough to clear the threshold on the first call, and assert there was exactly one call.

In `ai-video-platform/backend/tests/test_script_generator.py`, replace the existing `test_generate_script_long_requests_600_seconds` function with:

```python
def test_generate_script_long_requests_600_seconds():
    long_text = " ".join(["word"] * 1400)  # above the 1350-word continuation threshold
    payload = json.dumps({
        "title": "The Full History of Rome",
        "mood": "dramatic",
        "scenes": [
            {"text": long_text, "keywords": ["rome", "history"], "duration_sec": 600},
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
    MockClient.return_value.chat.completions.create.assert_called_once()
```

- [ ] **Step 2: Add the four new tests for continuation behavior**

Append to `ai-video-platform/backend/tests/test_script_generator.py` (after the test from Step 1, anywhere before the end of the file):

```python
def test_generate_script_long_continues_when_under_word_threshold():
    first_text = " ".join(["alpha"] * 1300)  # below the 1350-word threshold
    first_payload = json.dumps({
        "title": "Long Topic",
        "mood": "calm",
        "scenes": [{"text": first_text, "keywords": ["a"], "duration_sec": 600}],
        "duration_sec": 600,
    })
    continuation_text = " ".join(["beta"] * 100)  # pushes combined total over the threshold
    continuation_payload = json.dumps({
        "scenes": [{"text": continuation_text, "keywords": ["b"], "duration_sec": 20}],
    })

    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = [
            _mock_openai(first_payload),
            _mock_openai(continuation_payload),
        ]
        script = generate_script("topic", "long")

    assert MockClient.return_value.chat.completions.create.call_count == 2
    assert script.body.startswith("alpha")
    assert "beta" in script.body
    assert len(script.scenes) == 2

def test_generate_script_long_gives_up_after_max_continuations():
    first_text = " ".join(["alpha"] * 10)  # far below threshold
    first_payload = json.dumps({
        "title": "Long Topic",
        "mood": "calm",
        "scenes": [{"text": first_text, "keywords": ["a"], "duration_sec": 600}],
        "duration_sec": 600,
    })
    continuation_text = " ".join(["beta"] * 10)  # still far below threshold each time
    continuation_payload = json.dumps({
        "scenes": [{"text": continuation_text, "keywords": ["b"], "duration_sec": 20}],
    })

    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = [
            _mock_openai(first_payload),
            _mock_openai(continuation_payload),
            _mock_openai(continuation_payload),
            _mock_openai(continuation_payload),
        ]
        script = generate_script("topic", "long")

    assert MockClient.return_value.chat.completions.create.call_count == 4  # 1 initial + 3 continuations (max)
    assert len(script.scenes) == 4
    assert script.duration_sec == 600

def test_generate_script_long_returns_accumulated_when_continuation_json_invalid():
    first_text = " ".join(["alpha"] * 10)
    first_payload = json.dumps({
        "title": "Long Topic",
        "mood": "calm",
        "scenes": [{"text": first_text, "keywords": ["a"], "duration_sec": 600}],
        "duration_sec": 600,
    })
    bad_continuation = _mock_openai("not valid json {{")

    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = [
            _mock_openai(first_payload),
            bad_continuation, bad_continuation, bad_continuation,  # exhausts max_retries=3 for the continuation
        ]
        script = generate_script("topic", "long")

    assert len(script.scenes) == 1
    assert script.body == first_text

def test_generate_script_short_never_continues():
    payload = json.dumps({
        "title": "Short Topic",
        "mood": "calm",
        "scenes": [{"text": "Just a few words.", "keywords": ["x"], "duration_sec": 5}],
        "duration_sec": 50,
    })
    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_openai(payload)
        script = generate_script("topic", "short")

    MockClient.return_value.chat.completions.create.assert_called_once()
    assert script.duration_sec == 50
```

- [ ] **Step 3: Run the test suite to verify the new/changed tests fail**

Run: `cd "D:\Нова папка\ai-video-platform" && python -m pytest backend/tests/test_script_generator.py -v`
Expected: `test_generate_script_long_requests_600_seconds` fails (call count assertion, since no continuation loop exists yet so behavior differs from what's asserted is irrelevant — actually with no continuation loop this test will currently PASS since there's only ever one call already). The four new tests fail with `AttributeError` or assertion errors (e.g. `call_count == 2` failing because there's no continuation logic yet, so the mock is only called once and extra queued side_effect values are unused — this will surface as a length/count mismatch in the assertions, not a crash). Confirm at least the 4 new tests show as FAILED.

- [ ] **Step 4: Implement the continuation loop**

Replace the full contents of `ai-video-platform/backend/pipeline/script_generator.py` with:

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

Format: horizontal YouTube video, exactly 10 minutes of narration (600 seconds)
Required length: at least 1500 words of narration text across all scenes combined, and at least 45 scenes. This is a STRICT MINIMUM, not a suggestion — a short summary is NOT acceptable for this task.

Rules:
- Start with a calm, welcoming introduction scene (not an abrupt hook).
- Cover the topic in real depth: break it into many distinct sub-topics, examples, stories, or angles — do not just give a brief overview and stop.
- Each scene should be 8-15 seconds long (roughly 20-35 words of narration) and cover one sub-topic or idea.
- Keep writing scenes until the combined narration across all scenes reaches the required length. Before finalizing, count the scenes and estimate the total words — if it is under 1500 words or under 45 scenes, keep adding more scenes covering additional angles of the topic.
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

_MODEL_BY_FORMAT = {"short": "gpt-4o-mini", "long": "gpt-4o"}

_LONG_TARGET_WORDS = 1500
_LONG_MIN_RATIO = 0.9
_LONG_MAX_CONTINUATIONS = 3

def _strip_markdown_code_fence(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw[raw.index("\n") + 1:]
        if raw.endswith("```"):
            raw = raw[:-3]
    return raw.strip()

def _continue_prompt(word_count: int, target: int) -> str:
    missing = target - word_count
    return (
        f"Your script so far has {word_count} words, but the target is at least {target} words. "
        f"Write approximately {missing} more words of NEW scenes covering NEW aspects of the topic "
        "that have not been covered yet — do not repeat or rephrase anything already written.\n\n"
        "Respond with JSON only — no markdown, no explanation:\n"
        '{"scenes": [{"text": "narration text for this scene", "keywords": ["visual1", "visual2"], "duration_sec": 10}]}'
    )

def _call_model(client, model, messages):
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()

def _request_full_script(client, model, messages, max_retries):
    raw = ""
    for attempt in range(max_retries):
        raw = _call_model(client, model, messages)
        try:
            data = json.loads(_strip_markdown_code_fence(raw))
            _ = data["title"]
            _ = data["duration_sec"]
            for s in data["scenes"]:
                _ = s["text"]
                _ = s["keywords"]
                _ = s["duration_sec"]
            return data, raw
        except (json.JSONDecodeError, KeyError):
            if attempt == max_retries - 1:
                raise ValueError(f"Script generator failed after {max_retries} attempts. Last response: {raw[:200]}")
    raise ValueError(f"Script generator failed after {max_retries} attempts. Last response: {raw[:200]}")

def _request_continuation(client, model, messages, max_retries):
    raw = ""
    for attempt in range(max_retries):
        raw = _call_model(client, model, messages)
        try:
            data = json.loads(_strip_markdown_code_fence(raw))
            scenes = data["scenes"]
            for s in scenes:
                _ = s["text"]
                _ = s["keywords"]
                _ = s["duration_sec"]
            return scenes, raw
        except (json.JSONDecodeError, KeyError):
            continue
    return None, raw

def generate_script(topic: str, format: str, max_retries: int = 3) -> Script:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = _SHORT_PROMPT if format == "short" else _LONG_PROMPT
    model = _MODEL_BY_FORMAT.get(format, "gpt-4o-mini")

    messages = [
        {"role": "system", "content": "You are a professional video script writer. Always respond with valid JSON only."},
        {"role": "user", "content": prompt.format(topic=topic)},
    ]

    data, raw = _request_full_script(client, model, messages, max_retries)
    scenes = [
        Scene(text=s["text"], keywords=s["keywords"], duration_sec=s["duration_sec"])
        for s in data["scenes"]
    ]
    title = data["title"]
    mood = data.get("mood", "corporate")
    duration_sec = data["duration_sec"]

    if format == "long":
        messages.append({"role": "assistant", "content": raw})
        threshold = int(_LONG_TARGET_WORDS * _LONG_MIN_RATIO)
        word_count = len(" ".join(scene.text for scene in scenes).split())
        continuations = 0

        while word_count < threshold and continuations < _LONG_MAX_CONTINUATIONS:
            continuation_prompt = _continue_prompt(word_count, _LONG_TARGET_WORDS)
            continuation_messages = messages + [{"role": "user", "content": continuation_prompt}]
            new_scenes_data, new_raw = _request_continuation(client, model, continuation_messages, max_retries)
            continuations += 1

            if new_scenes_data is None:
                break

            scenes.extend(
                Scene(text=s["text"], keywords=s["keywords"], duration_sec=s["duration_sec"])
                for s in new_scenes_data
            )
            messages.append({"role": "user", "content": continuation_prompt})
            messages.append({"role": "assistant", "content": new_raw})
            word_count = len(" ".join(scene.text for scene in scenes).split())

        duration_sec = 600

    body = " ".join(scene.text for scene in scenes)
    return Script(title=title, scenes=scenes, body=body, mood=mood, duration_sec=duration_sec)
```

- [ ] **Step 5: Run the full test file to verify everything passes**

Run: `cd "D:\Нова папка\ai-video-platform" && python -m pytest backend/tests/test_script_generator.py -v`
Expected: all 10 tests pass (`test_generate_script_short_returns_script_dataclass`, `test_generate_script_long_requests_600_seconds`, `test_generate_script_retries_on_invalid_json`, `test_generate_script_defaults_mood_when_missing`, `test_generate_script_strips_markdown_code_fence`, `test_generate_script_body_joins_scene_texts`, `test_generate_script_long_continues_when_under_word_threshold`, `test_generate_script_long_gives_up_after_max_continuations`, `test_generate_script_long_returns_accumulated_when_continuation_json_invalid`, `test_generate_script_short_never_continues`).

- [ ] **Step 6: Run the full backend + bot test suites to confirm no regressions elsewhere**

Run: `cd "D:\Нова папка\ai-video-platform" && python -m pytest backend/tests bot/tests -v`
Expected: all tests pass (51 existing + the new ones from Step 5 above this file, i.e. 51 - 6 old script_generator tests + 10 new script_generator tests = 55 total — exact count isn't critical, zero failures is).

- [ ] **Step 7: Commit**

```bash
cd ai-video-platform
git add backend/pipeline/script_generator.py backend/tests/test_script_generator.py
git commit -m "feat: iteratively grow long-format scripts toward the 1500-word target

Long-format scripts from a single GPT call systematically fall short
of the 1500-word / 45-scene target (see
docs/superpowers/specs/2026-06-18-long-script-length-design.md for
measurements). Now, after the first valid response, if it's under
90% of the target word count, the code asks for up to 3 follow-up
batches of new scenes in the same conversation, stopping early once
the threshold is met. If a continuation never produces valid JSON,
the loop stops and returns the accumulated (possibly still short)
script rather than failing the whole pipeline run."
```

---

### Task 2: Manual verification against the real OpenAI API

**Files:** none — this is a manual verification checklist.

- [ ] **Step 1: Run a real long-format generation and inspect word/scene counts**

From `ai-video-platform/`, with a valid `OPENAI_API_KEY` in `.env`, run:

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from backend.pipeline.script_generator import generate_script
script = generate_script('the history of coffee', 'long')
word_count = len(script.body.split())
print(f'title: {script.title}')
print(f'scenes: {len(script.scenes)}')
print(f'words: {word_count}')
print(f'duration_sec: {script.duration_sec}')
"
```

Expected: `words` is at or close to 1500 (at least 1350, the 90% threshold — it's fine if it's still a bit short after 3 continuations, that's the documented graceful-degradation behavior), `scenes` is at or close to 45, `duration_sec` prints `600`. This call makes up to 4 real OpenAI API calls (gpt-4o) — costs a small amount of real API credit, no video rendering involved (cheap/fast way to validate per the spec's testing section).

- [ ] **Step 2: Update session history**

Add a short entry to `docs/session-history.md` noting: the iterative growth feature from `docs/superpowers/plans/2026-06-18-long-script-iterative-growth.md` was implemented, the actual word/scene counts observed in Step 1, and that this closes out the design from `docs/superpowers/specs/2026-06-18-long-script-length-design.md`.
