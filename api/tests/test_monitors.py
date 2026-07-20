"""Tests for monitors CRUD, feed, timeline and timeline caching."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_cache, get_monitors, get_search
from api.models import Monitor, MonitorCreate


class FakeMonitors:
    def __init__(self) -> None:
        self.store: dict[str, Monitor] = {}

    async def create(self, payload: MonitorCreate) -> Monitor:
        m = Monitor(
            id=f"m{len(self.store) + 1}",
            created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
            **payload.model_dump(),
        )
        self.store[m.id] = m
        return m

    async def list(self) -> list[Monitor]:
        return list(self.store.values())

    async def get(self, monitor_id: str) -> Monitor | None:
        return self.store.get(monitor_id)

    async def delete(self, monitor_id: str) -> bool:
        return self.store.pop(monitor_id, None) is not None


class FakeSearch:
    def __init__(self) -> None:
        self.timeline_calls = 0

    async def feed(self, monitor_id: str, limit: int = 20, offset: int = 0) -> dict:
        return {"total": 1, "limit": limit, "offset": offset,
                "results": [{"id": "a1", "title": "hit", "matched_monitor_ids": [monitor_id]}]}

    async def timeline(self, monitor_id, interval="1h", date_from=None, date_to=None) -> dict:
        self.timeline_calls += 1
        return {"monitor_id": monitor_id, "interval": interval,
                "points": [{"time": "2026-07-21T00:00:00.000Z", "count": 3}]}


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    async def get(self, key: str) -> dict | None:
        return self.store.get(key)

    async def set(self, key: str, value: dict) -> None:
        self.store[key] = value


@pytest.fixture
def client():
    monitors, search, cache = FakeMonitors(), FakeSearch(), FakeCache()
    app.dependency_overrides[get_monitors] = lambda: monitors
    app.dependency_overrides[get_search] = lambda: search
    app.dependency_overrides[get_cache] = lambda: cache
    try:
        yield TestClient(app), search
    finally:
        app.dependency_overrides.clear()


def test_create_list_delete_monitor(client):
    c, _ = client
    resp = c.post("/monitors", json={"name": "py", "keywords": ["python", " ", "fastapi"]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["keywords"] == ["python", "fastapi"]  # blanks stripped
    mid = body["id"]

    assert [m["id"] for m in c.get("/monitors").json()] == [mid]

    assert c.delete(f"/monitors/{mid}").status_code == 204
    assert c.get("/monitors").json() == []
    assert c.delete(f"/monitors/{mid}").status_code == 404


def test_create_monitor_requires_a_keyword(client):
    c, _ = client
    assert c.post("/monitors", json={"name": "x", "keywords": []}).status_code == 422
    assert c.post("/monitors", json={"name": "x", "keywords": ["  "]}).status_code == 422


def test_feed_404_for_unknown_monitor(client):
    c, _ = client
    assert c.get("/monitors/nope/feed").status_code == 404


def test_feed_returns_matches(client):
    c, _ = client
    mid = c.post("/monitors", json={"name": "py", "keywords": ["python"]}).json()["id"]
    body = c.get(f"/monitors/{mid}/feed").json()
    assert body["total"] == 1
    assert body["results"][0]["matched_monitor_ids"] == [mid]


def test_timeline_is_cached_on_second_call(client):
    c, search = client
    mid = c.post("/monitors", json={"name": "py", "keywords": ["python"]}).json()["id"]

    first = c.get(f"/monitors/{mid}/timeline?interval=1h").json()
    assert first["cached"] is False
    assert first["points"][0]["count"] == 3

    second = c.get(f"/monitors/{mid}/timeline?interval=1h").json()
    assert second["cached"] is True
    # ES aggregation ran only once; the repeat was served from cache.
    assert search.timeline_calls == 1
