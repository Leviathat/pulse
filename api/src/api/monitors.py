"""ElasticSearch-backed storage for monitors (the write model)."""

import uuid
from datetime import datetime, timezone

from elasticsearch import AsyncElasticsearch, NotFoundError

from api.models import Monitor, MonitorCreate

MONITORS_INDEX = "monitors"

MONITORS_MAPPING = {
    "mappings": {
        "properties": {
            "name": {"type": "text"},
            "keywords": {"type": "keyword"},
            "created_at": {"type": "date"},
        }
    }
}


class MonitorRepository:
    """CRUD for monitors. Writes refresh the index so reads are immediately consistent."""

    def __init__(self, client: AsyncElasticsearch, index: str = MONITORS_INDEX) -> None:
        self._client = client
        self._index = index

    async def ensure_index(self) -> None:
        if not await self._client.indices.exists(index=self._index):
            await self._client.indices.create(index=self._index, **MONITORS_MAPPING)

    async def create(self, payload: MonitorCreate) -> Monitor:
        monitor = Monitor(
            id=uuid.uuid4().hex,
            created_at=datetime.now(timezone.utc),
            **payload.model_dump(),
        )
        doc = monitor.model_dump(mode="json", exclude={"id"})
        await self._client.index(
            index=self._index, id=monitor.id, document=doc, refresh=True
        )
        return monitor

    async def list(self) -> list[Monitor]:
        resp = await self._client.search(
            index=self._index,
            query={"match_all": {}},
            sort=[{"created_at": {"order": "desc"}}],
            size=1000,
            ignore_unavailable=True,
        )
        hits = resp.get("hits", {}).get("hits", [])
        return [Monitor(id=h["_id"], **h["_source"]) for h in hits]

    async def get(self, monitor_id: str) -> Monitor | None:
        try:
            resp = await self._client.get(index=self._index, id=monitor_id)
        except NotFoundError:
            return None
        return Monitor(id=resp["_id"], **resp["_source"])

    async def delete(self, monitor_id: str) -> bool:
        try:
            await self._client.delete(index=self._index, id=monitor_id, refresh=True)
        except NotFoundError:
            return False
        return True
