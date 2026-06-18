from unittest.mock import patch, AsyncMock, MagicMock

from bot import client


def _mock_async_client(response: MagicMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.post.return_value = response
    mock_client.get.return_value = response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


async def test_create_video_returns_parsed_json():
    response = MagicMock()
    response.json.return_value = {"id": "abc"}
    response.raise_for_status.return_value = None
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        result = await client.create_video("AI news", "short")

    assert result == {"id": "abc"}
    mock_client.post.assert_called_once_with(
        "/videos/", json={"topic": "AI news", "format": "short"}
    )


async def test_get_status_returns_parsed_json():
    response = MagicMock()
    response.json.return_value = {"status": "completed"}
    response.raise_for_status.return_value = None
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        result = await client.get_status("vid-1")

    assert result == {"status": "completed"}
    mock_client.get.assert_called_once_with("/videos/vid-1/status")


async def test_create_video_raises_on_http_error():
    response = MagicMock()
    response.raise_for_status.side_effect = Exception("boom")
    mock_client = _mock_async_client(response)

    with patch("bot.client.httpx.AsyncClient", return_value=mock_client):
        try:
            await client.create_video("AI news", "short")
            assert False, "expected an exception"
        except Exception as exc:
            assert str(exc) == "boom"
