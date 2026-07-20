"""Domain model for an article event, mirroring the ingestor's Kafka contract."""

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field


class Article(BaseModel):
    """A normalized article as published to `raw_articles` (see pulse-tz.md 4.1)."""

    source: str
    source_id: str
    url: str
    title: str
    body: str = ""
    author: str = ""
    published_at: datetime
    fetched_at: datetime

    @property
    def doc_id(self) -> str:
        """Deterministic ES `_id` so reprocessing an event never duplicates it."""
        return hashlib.sha256(f"{self.source}:{self.source_id}".encode()).hexdigest()


class EnrichedArticle(Article):
    """An article augmented with fields computed by the processor before indexing."""

    lang: str = "unknown"
    matched_monitor_ids: list[str] = Field(default_factory=list)
