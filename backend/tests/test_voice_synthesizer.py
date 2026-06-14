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
