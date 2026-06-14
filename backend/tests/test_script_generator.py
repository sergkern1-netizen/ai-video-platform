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
