import os
from dataclasses import dataclass, field
from typing import Literal
import httpx
from backend.pipeline.script_generator import Scene

PEXELS_API_URL = "https://api.pexels.com/videos/search"

_ORIENTATION_BY_FORMAT = {"short": "portrait", "long": "landscape"}

@dataclass
class Assets:
    video_clips: list[dict | None] = field(default_factory=list)  # aligned with scenes

def fetch_assets(scenes: list[Scene], format: Literal["short", "long"], clip_dir: str = "temp") -> Assets:
    orientation = _ORIENTATION_BY_FORMAT.get(format, "landscape")
    clips = []
    last_successful = None

    for scene in scenes:
        clip = _fetch_scene_clip(scene, orientation, clip_dir)
        if clip is None:
            clip = last_successful
        else:
            last_successful = clip
        clips.append(clip)

    return Assets(video_clips=clips)

def _fetch_scene_clip(scene: Scene, orientation: str, clip_dir: str) -> dict | None:
    query = " ".join(scene.keywords[:2])
    try:
        resp = httpx.get(
            PEXELS_API_URL,
            headers={"Authorization": os.environ["PEXELS_API_KEY"]},
            params={"query": query, "per_page": 5, "min_duration": 5, "orientation": orientation},
            timeout=15,
        )
        videos = resp.json().get("videos", [])
    except Exception:
        return None

    if not videos:
        return None

    os.makedirs(clip_dir, exist_ok=True)
    for video in videos:
        files = sorted(
            video["video_files"],
            key=lambda f: f.get("width", 0),
            reverse=True,
        )
        best = next((f for f in files if f.get("width", 0) >= 1080), files[0])
        clip_path = os.path.join(clip_dir, f"{video['id']}.mp4")
        try:
            _download_clip(best["link"], clip_path)
            return {"path": clip_path, "duration_sec": video["duration"]}
        except Exception:
            continue

    return None

def _download_clip(url: str, path: str) -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            with open(path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
