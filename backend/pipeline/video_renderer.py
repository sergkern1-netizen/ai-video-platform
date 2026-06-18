import os
from functools import lru_cache
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


@lru_cache(maxsize=4)
def _get_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_FONT_PATH, size)


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
    scene_count = len(script.scenes)
    crossfade_compensation = _CROSSFADE_SEC * (scene_count - 1) if scene_count > 1 else 0
    scale = (duration + crossfade_compensation) / total_planned

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
    if not duration or duration <= 0:
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

    # moviepy's crossfadein() attaches a fade mask to a clip's ENTIRE duration,
    # not just the transition window, which forces every frame of that clip
    # through CompositeVideoClip's expensive masked alpha-blend path instead of
    # the cheap copy-only path. Building short, separate transition clips that
    # cover only the actual _CROSSFADE_SEC overlap keeps that expensive path
    # confined to a handful of frames per transition instead of whole scenes.
    segments = []
    for i, clip in enumerate(clips):
        start_trim = _CROSSFADE_SEC if i > 0 else 0
        end_trim = _CROSSFADE_SEC if i < len(clips) - 1 else 0
        segments.append(clip.subclip(start_trim, clip.duration - end_trim))

    transitions = []
    for a, b in zip(clips[:-1], clips[1:]):
        a_tail = a.subclip(a.duration - _CROSSFADE_SEC, a.duration)
        b_head = b.subclip(0, _CROSSFADE_SEC).crossfadein(_CROSSFADE_SEC)
        transitions.append(CompositeVideoClip([a_tail, b_head]))

    ordered = [segments[0]]
    for transition, segment in zip(transitions, segments[1:]):
        ordered.append(transition)
        ordered.append(segment)

    return concatenate_videoclips(ordered, method="chain")


def _group_words_into_windows(word_timings: list, window_size: int = _KARAOKE_WINDOW) -> list:
    return [
        word_timings[i : i + window_size]
        for i in range(0, len(word_timings), window_size)
    ]


_KARAOKE_PAD = 8


def _make_karaoke_clips(word_timings: list, size: tuple) -> list:
    clips = []
    for window in _group_words_into_windows(word_timings):
        for index, word in enumerate(window):
            clip_duration = word["end"] - word["start"]
            if clip_duration <= 0:
                continue
            img, position = _render_karaoke_frame(window, index, size)
            clip = (
                ImageClip(np.array(img), duration=clip_duration)
                .set_start(word["start"])
                .set_position(position)
            )
            clips.append(clip)
    return clips


def _render_karaoke_frame(window: list, active_index: int, size: tuple) -> tuple:
    # Cropped to the text's actual bounding box (plus small padding) instead
    # of a full-frame canvas: MoviePy's compositor does a masked alpha-blend
    # over the overlay's area on every frame it's shown, so a full 1920x1080
    # overlay for a few words of text is far more compositing work than needed.
    w, h = size
    font_size = 64 if w == 1080 else 46
    font = _get_font(font_size)
    measure_img = Image.new("RGBA", (1, 1))
    measure_draw = ImageDraw.Draw(measure_img)

    words = [entry["text"] for entry in window]
    spacing = 14
    max_width = w - 80

    lines = [[]]
    line_width = 0
    for idx, word in enumerate(words):
        bbox = measure_draw.textbbox((0, 0), word, font=font)
        word_w = bbox[2] - bbox[0]
        if line_width + word_w + spacing > max_width and lines[-1]:
            lines.append([])
            line_width = 0
        lines[-1].append(idx)
        line_width += word_w + spacing

    line_height = font_size + 16
    block_height = len(lines) * line_height
    y0 = h - block_height - 80

    line_data = []
    block_width = 0
    for line in lines:
        widths = []
        total_w = 0
        for idx in line:
            bbox = measure_draw.textbbox((0, 0), words[idx], font=font)
            word_w = bbox[2] - bbox[0]
            widths.append(word_w)
            total_w += word_w + spacing
        total_w -= spacing
        line_data.append((line, widths, total_w))
        block_width = max(block_width, total_w)

    pad = _KARAOKE_PAD
    img = Image.new("RGBA", (block_width + pad * 2, block_height + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    y = pad
    for line, widths, total_w in line_data:
        x = (block_width - total_w) // 2 + pad
        for idx, word_w in zip(line, widths):
            color = (255, 215, 0, 255) if idx == active_index else (255, 255, 255, 255)
            draw.text((x + 2, y + 2), words[idx], fill=(0, 0, 0, 200), font=font)
            draw.text((x, y), words[idx], fill=color, font=font)
            x += word_w + spacing
        y += line_height

    x_offset = (w - block_width) // 2 - pad
    y_offset = y0 - pad
    return img, (x_offset, y_offset)
