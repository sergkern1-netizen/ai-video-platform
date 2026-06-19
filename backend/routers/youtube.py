import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from redis import Redis
from rq import Queue

import backend.database as db
import backend.youtube.oauth as oauth
from backend.youtube.uploader import upload_video

router = APIRouter()

_redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
_queue = Queue(connection=_redis)


class StartConnectRequest(BaseModel):
    telegram_user_id: int


@router.post("/connect/start")
def start_connect(request: StartConnectRequest):
    auth_url = oauth.start_oauth(request.telegram_user_id)
    return {"auth_url": auth_url}


@router.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(code: str, state: str):
    telegram_user_id = oauth.pop_pending_user(state)
    if telegram_user_id is None:
        return HTMLResponse(
            "<h1>Ссылка устарела, начните заново через /connect_channel в боте.</h1>"
        )

    channel_info = oauth.exchange_code(code)
    db.create_youtube_channel(
        channel_info["channel_id"],
        channel_info["channel_title"],
        channel_info["refresh_token"],
        telegram_user_id,
    )
    _notify_telegram(telegram_user_id, f"Канал «{channel_info['channel_title']}» подключён!")
    return HTMLResponse("<h1>Готово! Возвращайтесь в Telegram.</h1>")


def _notify_telegram(user_id: int, text: str):
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": user_id, "text": text},
        timeout=10,
    )


@router.get("/channels")
def list_channels():
    channels = db.list_youtube_channels()
    return [{"id": c["id"], "channel_title": c["channel_title"]} for c in channels]


class PublishRequest(BaseModel):
    video_id: str
    channel_id: str
    title: str
    description: str


@router.post("/publish")
def publish(request: PublishRequest):
    video = db.get_video(request.video_id)
    if not video or video["status"] != "completed":
        raise HTTPException(status_code=404, detail="Video not ready")

    publish_row = db.create_publish(
        request.video_id, request.channel_id, request.title, request.description
    )
    _queue.enqueue(upload_video, publish_row["id"], job_timeout=1800)
    return {"id": publish_row["id"]}


@router.get("/publishes/{publish_id}/status")
def get_publish_status(publish_id: str):
    publish_row = db.get_publish(publish_id)
    if not publish_row:
        raise HTTPException(status_code=404, detail="Publish not found")
    return publish_row
