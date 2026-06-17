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

    word_timings = _whisper_word_timings(client, audio_path)
    if word_timings is None:
        word_timings = _estimate_timings(script.body, duration)

    return VoiceOutput(audio_path=audio_path, word_timings=word_timings)

def _whisper_word_timings(client: OpenAI, audio_path: str) -> list[dict] | None:
    try:
        with open(audio_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        return [
            {"text": w["word"], "start": w["start"], "end": w["end"]}
            for w in transcript.words
        ]
    except Exception:
        return None

def _estimate_timings(text: str, total_duration: float) -> list[dict]:
    words = text.split()
    if not words:
        return []
    time_per_word = total_duration / len(words)
    return [
        {
            "text": word,
            "start": round(i * time_per_word, 2),
            "end": round((i + 1) * time_per_word, 2),
        }
        for i, word in enumerate(words)
    ]
