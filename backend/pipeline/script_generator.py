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
