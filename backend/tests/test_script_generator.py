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

def test_generate_script_strips_markdown_code_fence():
    payload = json.dumps({
        "title": "Fenced Response",
        "mood": "calm",
        "scenes": [{"text": "Some text.", "keywords": ["x"], "duration_sec": 5}],
        "duration_sec": 50,
    })
    fenced = f"```json\n{payload}\n```"
    with patch("backend.pipeline.script_generator.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_openai(fenced)
        script = generate_script("topic", "short")

    assert script.title == "Fenced Response"

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
