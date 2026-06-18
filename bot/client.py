import httpx

from bot.config import get_backend_url


async def create_video(topic: str, format: str) -> dict:
    async with httpx.AsyncClient(base_url=get_backend_url(), timeout=10) as session:
        response = await session.post("/videos/", json={"topic": topic, "format": format})
        response.raise_for_status()
        return response.json()


async def get_status(video_id: str) -> dict:
    async with httpx.AsyncClient(base_url=get_backend_url(), timeout=10) as session:
        response = await session.get(f"/videos/{video_id}/status")
        response.raise_for_status()
        return response.json()
