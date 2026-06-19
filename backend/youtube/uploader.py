import os

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import backend.database as db


def _build_youtube_client(refresh_token: str):
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=credentials)


def upload_video(publish_id: str) -> None:
    publish = db.get_publish(publish_id)
    try:
        db.update_publish_status(publish_id, "uploading")

        channel = db.get_youtube_channel(publish["channel_id"])
        video = db.get_video(publish["video_id"])

        youtube = _build_youtube_client(channel["refresh_token"])
        media = MediaFileUpload(video["video_path"], chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": publish["title"],
                    "description": publish["description"],
                },
                "status": {"privacyStatus": publish["privacy"]},
            },
            media_body=media,
        )

        response = None
        while response is None:
            _, response = request.next_chunk()

        db.update_publish_status(publish_id, "completed", youtube_video_id=response["id"])

    except RefreshError:
        db.update_publish_status(
            publish_id, "failed",
            error="Канал отключён в Google, подключите заново через /connect_channel",
        )
        raise
    except Exception as exc:
        db.update_publish_status(publish_id, "failed", error=str(exc))
        raise
