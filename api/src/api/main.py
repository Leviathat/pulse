"""Pulse REST API: full-text search, monitors CRUD, feed and timeline.

Timeline responses are cached in Redis (cache-aside, short TTL) — the expensive
date_histogram aggregation is served from cache on repeat requests.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, AsyncIterator

from elasticsearch import AsyncElasticsearch
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from redis.asyncio import Redis

from api.cache import Cache
from api.config import Settings
from api.es import ArticleSearch
from api.models import Monitor, MonitorCreate
from api.monitors import MonitorRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.es = AsyncElasticsearch(settings.es_url)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.search = ArticleSearch(app.state.es)
    app.state.monitors = MonitorRepository(app.state.es)
    app.state.cache = Cache(app.state.redis, ttl_seconds=settings.cache_ttl_seconds)
    await app.state.monitors.ensure_index()
    try:
        yield
    finally:
        await app.state.es.close()
        await app.state.redis.aclose()


app = FastAPI(title="Pulse API", version="0.2.0", lifespan=lifespan)


def get_search() -> ArticleSearch:
    return app.state.search


def get_monitors() -> MonitorRepository:
    return app.state.monitors


def get_cache() -> Cache:
    return app.state.cache


SearchDep = Annotated[ArticleSearch, Depends(get_search)]
MonitorsDep = Annotated[MonitorRepository, Depends(get_monitors)]
CacheDep = Annotated[Cache, Depends(get_cache)]


async def _require_monitor(monitors: MonitorRepository, monitor_id: str) -> Monitor:
    monitor = await monitors.get(monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="monitor not found")
    return monitor


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search")
async def search(
    search: SearchDep,
    q: Annotated[str | None, Query(description="Full-text query over title/body")] = None,
    source: Annotated[str | None, Query(description="Filter by source")] = None,
    from_: Annotated[datetime | None, Query(alias="from", description="published_at >=")] = None,
    to: Annotated[datetime | None, Query(description="published_at <=")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Full-text search over the archived articles, newest first."""
    return await search.search(
        q=q, source=source, date_from=from_, date_to=to, limit=limit, offset=offset
    )


@app.post("/monitors", status_code=status.HTTP_201_CREATED)
async def create_monitor(payload: MonitorCreate, monitors: MonitorsDep) -> Monitor:
    return await monitors.create(payload)


@app.get("/monitors")
async def list_monitors(monitors: MonitorsDep) -> list[Monitor]:
    return await monitors.list()


@app.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(monitor_id: str, monitors: MonitorsDep) -> Response:
    if not await monitors.delete(monitor_id):
        raise HTTPException(status_code=404, detail="monitor not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/monitors/{monitor_id}/feed")
async def monitor_feed(
    monitor_id: str,
    monitors: MonitorsDep,
    search: SearchDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Articles matched to this monitor, newest first."""
    await _require_monitor(monitors, monitor_id)
    return await search.feed(monitor_id, limit=limit, offset=offset)


@app.get("/monitors/{monitor_id}/timeline")
async def monitor_timeline(
    monitor_id: str,
    monitors: MonitorsDep,
    search: SearchDep,
    cache: CacheDep,
    interval: Annotated[str, Query(description="date_histogram interval, e.g. 1h, 1d")] = "1h",
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> dict:
    """Mentions-over-time for a monitor. Cache-aside via Redis (short TTL)."""
    await _require_monitor(monitors, monitor_id)
    key = f"timeline:{monitor_id}:{interval}:{from_}:{to}"
    cached = await cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}
    result = await search.timeline(monitor_id, interval=interval, date_from=from_, date_to=to)
    await cache.set(key, result)
    return {**result, "cached": False}
