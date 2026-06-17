import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal

import backend.database as db
from backend.pipeline.asset_fetcher import fetch_assets
from backend.pipeline.script_generator import generate_script
from backend.pipeline.video_renderer import render_video
from backend.pipeline.voice_synthesizer import synthesize_voice

@dataclass
class PipelineInput:
    topic: str
    format: Literal["short", "long"]
    job_id: str

def run_pipeline(pipeline_input: PipelineInput) -> None:
    job_id = pipeline_input.job_id
    try:
        db.update_video_status(job_id, "processing")

        script = generate_script(pipeline_input.topic, pipeline_input.format)

        with ThreadPoolExecutor(max_workers=2) as executor:
            voice_future = executor.submit(synthesize_voice, script, job_id)
            assets_future = executor.submit(
                fetch_assets, script.scenes, pipeline_input.format
            )
            voice = voice_future.result()
            assets = assets_future.result()

        os.makedirs("output", exist_ok=True)
        output_path = os.path.join("output", f"{job_id}.mp4")
        render_video(script, voice, assets, pipeline_input.format, output_path)

        db.update_video_status(job_id, "completed", video_path=output_path)

    except Exception as exc:
        db.update_video_status(job_id, "failed", error=str(exc))
        raise
