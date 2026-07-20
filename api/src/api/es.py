"""ElasticSearch read model: full-text search over the `articles` index."""

from datetime import datetime

from elasticsearch import AsyncElasticsearch

ARTICLES_INDEX = "articles"


def build_search_query(
    q: str | None,
    source: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict:
    """Translate search parameters into an ES bool query.

    `q` drives full-text relevance across title/body; source and date act as
    filters (no scoring). With no `q` and no filters this matches everything,
    sorted by recency.
    """
    must: list[dict] = []
    if q:
        must.append({"multi_match": {"query": q, "fields": ["title^2", "body"]}})

    filters: list[dict] = []
    if source:
        filters.append({"term": {"source": source}})
    if date_from or date_to:
        rng: dict[str, str] = {}
        if date_from:
            rng["gte"] = date_from.isoformat()
        if date_to:
            rng["lte"] = date_to.isoformat()
        filters.append({"range": {"published_at": rng}})

    if not must and not filters:
        return {"match_all": {}}
    return {"bool": {"must": must or [{"match_all": {}}], "filter": filters}}


class ArticleSearch:
    """Queries the articles index and shapes hits for the API response."""

    def __init__(self, client: AsyncElasticsearch, index: str = ARTICLES_INDEX) -> None:
        self._client = client
        self._index = index

    async def search(
        self,
        q: str | None = None,
        source: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        query = build_search_query(q, source, date_from, date_to)
        resp = await self._client.search(
            index=self._index,
            query=query,
            sort=[{"published_at": {"order": "desc"}}],
            from_=offset,
            size=limit,
            ignore_unavailable=True,  # empty result before the index exists
        )
        hits = resp.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        results = [{"id": h["_id"], **h["_source"]} for h in hits.get("hits", [])]
        return {"total": total, "limit": limit, "offset": offset, "results": results}
