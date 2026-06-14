import os
from dataclasses import dataclass
from openai import OpenAI
from moviepy.editor import AudioFileClip
from backend.pipeline.script_generator import Script

@dataclass
class VoiceOutput:
    audio_path: str
    word_timings: list[dict]  # [{text, start, end}]

def synthesize_voice(script: Script, job_id: str, audio_dir: str = "temp") -> VoiceOutput:
    os.makedirs(audio_dir, exist_ok=True)
    audio_path = os.path.join(audio_dir, f"{job_id}.mp3")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=script.body,
    )
    response.stream_to_file(audio_path)

    clip = AudioFileClip(audio_path)
    duration = clip.duration
    clip.close()

    word_timings = _estimate_timings(script.body, duration)
    return VoiceOutput(audio_path=audio_path, word_timings=word_timings)

def _estimate_timings(text: str, total_duration: float) -> list[dict]:
    words = text.split()
    chunk_size = 8
    chunks = [
        " ".join(words[i : i + chunk_size])
        for i in range(0, len(words), chunk_size)
    ]
    if not chunks:
        return []
    time_per_chunk = total_duration / len(chunks)
    return [
        {
            "text": chunk,
            "start": round(i * time_per_chunk, 2),
            "end": round((i + 1) * time_per_chunk, 2),
        }
        for i, chunk in enumerate(chunks)
    ]
