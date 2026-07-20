"""Keyword matching of articles against active monitors.

Matching happens on write: each incoming article is tagged with the ids of the
monitors whose keywords it contains, so feeds are a cheap term lookup at read
time. Monitors are loaded from ES and cached with a short TTL, so newly created
monitors take effect within `ttl` seconds without querying ES per message.
"""

import logging
import re
import time

from elasticsearch import AsyncElasticsearch

from processor.models import Monitor

log = logging.getLogger("processor.matching")

MONITORS_INDEX = "monitors"


class Matcher:
    """Matches text against a fixed set of monitors using word-boundary search."""

    def __init__(self, monitors: list[Monitor]) -> None:
        self._compiled: list[tuple[str, list[re.Pattern[str]]]] = [
            (m.id, self._compile(m.keywords)) for m in monitors
        ]

    @staticmethod
    def _compile(keywords: list[str]) -> list[re.Pattern[str]]:
        pats = []
        for kw in keywords:
            kw = kw.strip()
            if kw:
                pats.append(re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
        return pats

    def match(self, text: str) -> list[str]:
        """Return ids of monitors with at least one keyword present in `text`."""
        return [
            monitor_id
            for monitor_id, patterns in self._compiled
            if any(p.search(text) for p in patterns)
        ]


class MonitorRepository:
    """Reads active monitors from the ES `monitors` index."""

    def __init__(self, client: AsyncElasticsearch, index: str = MONITORS_INDEX) -> None:
        self._client = client
        self._index = index

    async def list_active(self) -> list[Monitor]:
        resp = await self._client.search(
            index=self._index,
            query={"match_all": {}},
            size=1000,
            ignore_unavailable=True,  # index may not exist until a monitor is created
        )
        hits = resp.get("hits", {}).get("hits", [])
        return [Monitor(id=h["_id"], **h["_source"]) for h in hits]


class MonitorCache:
    """Caches a compiled Matcher, refreshing from ES at most once per `ttl` seconds."""

    def __init__(self, repo: MonitorRepository, ttl: float = 30.0) -> None:
        self._repo = repo
        self._ttl = ttl
        self._matcher = Matcher([])
        self._loaded_at = 0.0

    async def matcher(self) -> Matcher:
        now = time.monotonic()
        if now - self._loaded_at >= self._ttl:
            try:
                monitors = await self._repo.list_active()
                self._matcher = Matcher(monitors)
                self._loaded_at = now
                log.info("loaded %d active monitor(s)", len(monitors))
            except Exception as exc:  # noqa: BLE001 — keep last matcher on failure
                log.warning("failed to refresh monitors: %s", exc)
        return self._matcher
