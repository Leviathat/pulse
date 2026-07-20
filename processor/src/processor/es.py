"""ElasticSearch repository: index bootstrap and idempotent article writes."""

import asyncio
import logging

from elasticsearch import AsyncElasticsearch

from processor.models import EnrichedArticle

log = logging.getLogger("processor.es")

ARTICLES_INDEX = "articles"

# title/body are full-text; identifiers/dates are exact-match keyword/date.
ARTICLES_MAPPING = {
    "mappings": {
        "properties": {
            "source": {"type": "keyword"},
            "source_id": {"type": "keyword"},
            "url": {"type": "keyword"},
            "title": {"type": "text"},
            "body": {"type": "text"},
            "author": {"type": "keyword"},
            "published_at": {"type": "date"},
            "fetched_at": {"type": "date"},
            "lang": {"type": "keyword"},
            "matched_monitor_ids": {"type": "keyword"},
        }
    }
}


class ArticleRepository:
    """Writes enriched articles into the `articles` index, keyed by doc_id."""

    def __init__(self, client: AsyncElasticsearch, index: str = ARTICLES_INDEX) -> None:
        self._client = client
        self._index = index

    async def ensure_index(self, retries: int = 30, delay: float = 2.0) -> None:
        """Create the index if missing, waiting for ES to come up first."""
        for attempt in range(1, retries + 1):
            try:
                if not await self._client.indices.exists(index=self._index):
                    await self._client.indices.create(index=self._index, **ARTICLES_MAPPING)
                    log.info("created index %s", self._index)
                else:
                    log.info("index %s already exists", self._index)
                return
            except Exception as exc:  # noqa: BLE001 — ES not ready yet, keep retrying
                log.warning("ES not ready (%d/%d): %s", attempt, retries, exc)
                await asyncio.sleep(delay)
        raise RuntimeError(f"ElasticSearch unavailable after {retries} attempts")

    async def index(self, article: EnrichedArticle) -> None:
        """Upsert one article. Same event → same doc_id → no duplicates."""
        await self._client.index(
            index=self._index,
            id=article.doc_id,
            document=article.model_dump(mode="json"),
        )
