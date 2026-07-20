"""Pulse REST API.

Stage 1 exposes full-text search over the indexed archive. Monitors CRUD, feed,
timeline and Redis caching arrive in stage 2.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, AsyncIterator

from elasticsearch import AsyncElasticsearch
from fastapi import Depends, FastAPI, Query

from api.config import Settings
from api.es import ArticleSearch


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.es = AsyncElasticsearch(settings.es_url)
    app.state.search = ArticleSearch(app.state.es)
    try:
        yield
    finally:
        await app.state.es.close()


app = FastAPI(title="Pulse API", version="0.1.0", lifespan=lifespan)


def get_search() -> ArticleSearch:
    return app.state.search


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search")
async def search(
    search: Annotated[ArticleSearch, Depends(get_search)],
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
