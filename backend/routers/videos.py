import os
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from redis import Redis
from rq import Queue

import backend.database as db
from backend.pipeline.runner import PipelineInput, run_pipeline

router = APIRouter()

_redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
_queue = Queue(connection=_redis)


class CreateVideoRequest(BaseModel):
    topic: str
    format: Literal["short", "long"]


@router.post("/")
def create_video(request: CreateVideoRequest):
    video_id = str(uuid4())
    db.create_video(video_id, request.topic, request.format)
    _queue.enqueue(
        run_pipeline,
        PipelineInput(topic=request.topic, format=request.format, job_id=video_id),
    )
    return {"id": video_id}


@router.get("/{video_id}/status")
def get_status(video_id: str):
    video = db.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{video_id}/download")
def download_video(video_id: str):
    video = db.get_video(video_id)
    if not video or video["status"] != "completed":
        raise HTTPException(status_code=404, detail="Video not ready")
    return FileResponse(
        video["video_path"],
        media_type="video/mp4",
        filename=f"{video_id}.mp4",
    )
