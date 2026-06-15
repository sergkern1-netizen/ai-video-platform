import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
)
from backend.pipeline.script_generator import Script
from backend.pipeline.voice_synthesizer import VoiceOutput
from backend.pipeline.asset_fetcher import Assets

_SIZES = {
    "short": (1080, 1920),
    "long": (1920, 1080),
}

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

    background = _build_background(assets, size, duration)
    subtitle_clips = [
        _make_subtitle_clip(t["text"], size, t["end"] - t["start"])
        .set_start(t["start"])
        .set_end(t["end"])
        for t in voice.word_timings
    ]

    final = CompositeVideoClip([background] + subtitle_clips, size=size)
    final = final.set_audio(audio)
    final.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

def _build_background(assets: Assets, size: tuple, duration: float):
    if not assets.video_clips:
        return ColorClip(size=size, color=[20, 20, 40], duration=duration)

    clip_path = assets.video_clips[0]["path"]
    clip = VideoFileClip(clip_path)
    clip = clip.resize(size)
    if clip.duration < duration:
        clip = clip.loop(duration=duration)
    else:
        clip = clip.subclip(0, duration)
    return clip

def _make_subtitle_clip(text: str, size: tuple, duration: float) -> ImageClip:
    w, h = size
    font_size = 60 if w == 1080 else 42
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    words = text.split()
    lines, current = [], []
    for word in words:
        current.append(word)
        bbox = draw.textbbox((0, 0), " ".join(current), font=font)
        if bbox[2] > w - 80:
            current.pop()
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))

    line_height = font_size + 10
    y = h - len(lines) * line_height - 60
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (w - bbox[2]) // 2
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0, 200), font=font)
        draw.text((x, y), line, fill=(255, 255, 255, 255), font=font)
        y += line_height

    return ImageClip(np.array(img), duration=duration, ismask=False)
