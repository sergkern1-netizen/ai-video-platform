import os
from dataclasses import dataclass, field
import httpx

PEXELS_API_URL = "https://api.pexels.com/videos/search"

@dataclass
class Assets:
    video_clips: list[dict] = field(default_factory=list)  # [{path, duration_sec}]

def fetch_assets(keywords: list[str], duration_sec: int, clip_dir: str = "temp") -> Assets:
    query = " ".join(keywords[:2])
    try:
        resp = httpx.get(
            PEXELS_API_URL,
            headers={"Authorization": os.environ["PEXELS_API_KEY"]},
            params={"query": query, "per_page": 5, "min_duration": 5},
            timeout=15,
        )
        videos = resp.json().get("videos", [])
    except Exception:
        return Assets()

    if not videos:
        return Assets()

    os.makedirs(clip_dir, exist_ok=True)
    clips = []
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
            clips.append({"path": clip_path, "duration_sec": video["duration"]})
        except Exception:
            continue

    return Assets(video_clips=clips)

def _download_clip(url: str, path: str) -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            with open(path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
