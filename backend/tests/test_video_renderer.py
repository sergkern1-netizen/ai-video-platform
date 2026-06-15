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
