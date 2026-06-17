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
    _concatenate_with_crossfade,
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

def test_concatenate_with_crossfade_matches_expected_duration_formula():
    from moviepy.editor import ColorClip
    from backend.pipeline.video_renderer import _CROSSFADE_SEC

    n = 3
    per_clip_duration = 3.0
    clips = [ColorClip(size=(10, 10), color=[0, 0, 0], duration=per_clip_duration) for _ in range(n)]

    result = _concatenate_with_crossfade(clips)

    expected = n * (per_clip_duration - _CROSSFADE_SEC)
    assert result.duration == pytest.approx(expected)
