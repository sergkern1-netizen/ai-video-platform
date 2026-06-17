import os
from unittest.mock import patch, MagicMock
from backend.pipeline.script_generator import Script, Scene
from backend.pipeline.voice_synthesizer import synthesize_voice, VoiceOutput

def _make_script(body="Hello world this is a test script for synthesis."):
    return Script(
        title="Test",
        scenes=[Scene(text=body, keywords=["test"], duration_sec=50)],
        body=body,
        mood="calm",
        duration_sec=50,
    )

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
