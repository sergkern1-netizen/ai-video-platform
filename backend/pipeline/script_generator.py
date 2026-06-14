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
