import pytest

from bot import state


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test_bot.db")
    monkeypatch.setenv("BOT_DB_PATH", db_file)
    state.init_db()
    yield


def test_add_request_and_get_history():
    state.add_request("vid-1", 111, "AI trends", "short")
    history = state.get_history(111)
    assert len(history) == 1
    assert history[0]["video_id"] == "vid-1"
    assert history[0]["topic"] == "AI trends"
    assert history[0]["format"] == "short"


def test_get_history_filters_by_user():
    state.add_request("vid-1", 111, "Topic A", "short")
    state.add_request("vid-2", 222, "Topic B", "long")
    history = state.get_history(111)
    assert len(history) == 1
    assert history[0]["video_id"] == "vid-1"


def test_get_history_respects_limit():
    for i in range(7):
        state.add_request(f"vid-{i}", 111, f"Topic {i}", "short")
    history = state.get_history(111, limit=5)
    assert len(history) == 5


def test_get_history_empty_for_unknown_user():
    assert state.get_history(999) == []
