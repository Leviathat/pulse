"""Tests for the API's ES repositories, article search queries, and Redis cache."""

import asyncio

from elasticsearch import NotFoundError

from api.cache import Cache
from api.es import ArticleSearch
from api.main import app, get_cache, get_monitors, get_search
from api.models import MonitorCreate
from api.monitors import MonitorRepository


# --- MonitorRepository (ES CRUD) --------------------------------------------

class FakeMonitorES:
    """Minimal async ES double backed by an in-memory dict."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indices = self  # so repo._client.indices.<...> works
        self._exists = False

    # indices.*
    async def exists(self, index: str) -> bool:
        return self._exists

    async def create(self, index: str, **_: object) -> None:
        self._exists = True

    # document ops
    async def index(self, index: str, id: str, document: dict, **_: object) -> None:
        self.docs[id] = document

    async def get(self, index: str, id: str) -> dict:
        if id not in self.docs:
            raise NotFoundError("missing", None, None)
        return {"_id": id, "_source": self.docs[id]}

    async def delete(self, index: str, id: str, **_: object) -> None:
        if id not in self.docs:
            raise NotFoundError("missing", None, None)
        del self.docs[id]

    async def search(self, **_: object) -> dict:
        hits = [{"_id": k, "_source": v} for k, v in self.docs.items()]
        return {"hits": {"hits": hits}}


def test_monitor_repository_crud_roundtrip() -> None:
    es = FakeMonitorES()
    repo = MonitorRepository(es)  # type: ignore[arg-type]

    async def go() -> None:
        await repo.ensure_index()
        assert es._exists is True

        created = await repo.create(MonitorCreate(name="py", keywords=["python"]))
        assert created.id and created.name == "py"

        fetched = await repo.get(created.id)
        assert fetched is not None and fetched.keywords == ["python"]

        assert [m.id for m in await repo.list()] == [created.id]

        assert await repo.delete(created.id) is True
        assert await repo.get(created.id) is None
        assert await repo.delete(created.id) is False

    asyncio.run(go())


# --- ArticleSearch.feed / timeline ------------------------------------------

class FakeArticleES:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.last_kwargs: dict = {}

    async def search(self, **kwargs: object) -> dict:
        self.last_kwargs = kwargs
        return self.response


def test_feed_shapes_hits_and_filters_by_monitor() -> None:
    es = FakeArticleES(
        {"hits": {"total": {"value": 2}, "hits": [
            {"_id": "a1", "_source": {"title": "one"}},
            {"_id": "a2", "_source": {"title": "two"}},
        ]}}
    )
    search = ArticleSearch(es)  # type: ignore[arg-type]
    out = asyncio.run(search.feed("m1", limit=10, offset=5))
    assert out["total"] == 2
    assert [r["id"] for r in out["results"]] == ["a1", "a2"]
    assert es.last_kwargs["query"] == {"term": {"matched_monitor_ids": "m1"}}
    assert es.last_kwargs["from_"] == 5 and es.last_kwargs["size"] == 10


def test_timeline_maps_buckets_to_points() -> None:
    es = FakeArticleES(
        {"aggregations": {"per_interval": {"buckets": [
            {"key_as_string": "2026-07-21T00:00:00Z", "doc_count": 3},
            {"key_as_string": "2026-07-21T01:00:00Z", "doc_count": 0},
        ]}}}
    )
    search = ArticleSearch(es)  # type: ignore[arg-type]
    out = asyncio.run(search.timeline("m1", interval="1h"))
    assert out["interval"] == "1h"
    assert out["points"] == [
        {"time": "2026-07-21T00:00:00Z", "count": 3},
        {"time": "2026-07-21T01:00:00Z", "count": 0},
    ]
    agg = es.last_kwargs["aggregations"]["per_interval"]["date_histogram"]
    assert agg["fixed_interval"] == "1h"


def test_timeline_applies_date_range_filter() -> None:
    from datetime import datetime, timezone

    es = FakeArticleES({"aggregations": {"per_interval": {"buckets": []}}})
    search = ArticleSearch(es)  # type: ignore[arg-type]
    asyncio.run(
        search.timeline(
            "m1",
            interval="1d",
            date_from=datetime(2026, 7, 1, tzinfo=timezone.utc),
            date_to=datetime(2026, 7, 31, tzinfo=timezone.utc),
        )
    )
    filters = es.last_kwargs["query"]["bool"]["filter"]
    rng = next(f for f in filters if "range" in f)["range"]["published_at"]
    assert rng["gte"].startswith("2026-07-01")
    assert rng["lte"].startswith("2026-07-31")


# --- Cache ------------------------------------------------------------------

class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: int | None = None

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        self.ttl = ex


def test_cache_get_miss_then_set_then_hit() -> None:
    redis = FakeRedis()
    cache = Cache(redis, ttl_seconds=30)  # type: ignore[arg-type]

    async def go() -> None:
        assert await cache.get("k") is None
        await cache.set("k", {"a": 1})
        assert await cache.get("k") == {"a": 1}

    asyncio.run(go())
    assert redis.ttl == 30


# --- dependency providers ---------------------------------------------------

def test_dependency_providers_return_app_state() -> None:
    sentinel_search = object()
    sentinel_monitors = object()
    sentinel_cache = object()
    app.state.search = sentinel_search
    app.state.monitors = sentinel_monitors
    app.state.cache = sentinel_cache
    assert get_search() is sentinel_search
    assert get_monitors() is sentinel_monitors
    assert get_cache() is sentinel_cache
