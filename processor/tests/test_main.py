"""Unit tests for parsing, enrichment and the message handler."""

import asyncio
import json

from processor.config import Settings
from processor.enrich import detect_lang, enrich
from processor.es import ArticleRepository
from processor.main import handle_message
from processor.models import Article, EnrichedArticle

SAMPLE = {
    "source": "hackernews",
    "source_id": "38912345",
    "url": "https://example.com/x",
    "title": "FastAPI is a modern Python web framework",
    "body": "It is fast and easy to use for building APIs.",
    "author": "pg",
    "published_at": "2026-07-03T10:00:00Z",
    "fetched_at": "2026-07-03T10:00:05Z",
}


def test_defaults_match_spec() -> None:
    s = Settings()
    assert s.kafka_topic == "raw_articles"
    assert s.kafka_group_id == "pulse-processor"


def test_doc_id_is_deterministic_and_source_scoped() -> None:
    a = Article.model_validate(SAMPLE)
    assert a.doc_id == a.doc_id
    assert len(a.doc_id) == 64
    other = a.model_copy(update={"source_id": "999"})
    assert other.doc_id != a.doc_id


def test_detect_lang() -> None:
    assert detect_lang("The quick brown fox jumps over the lazy dog") == "en"
    assert detect_lang("   ") == "unknown"


def test_enrich_adds_lang_and_empty_matches() -> None:
    enriched = enrich(Article.model_validate(SAMPLE))
    assert isinstance(enriched, EnrichedArticle)
    assert enriched.lang == "en"
    assert enriched.matched_monitor_ids == []
    assert enriched.doc_id  # carried through


class FakeRepo:
    def __init__(self) -> None:
        self.indexed: list[EnrichedArticle] = []

    async def index(self, article: EnrichedArticle) -> None:
        self.indexed.append(article)


def test_handle_message_indexes_valid_event() -> None:
    repo = FakeRepo()
    asyncio.run(handle_message(repo, json.dumps(SAMPLE).encode()))
    assert len(repo.indexed) == 1
    assert repo.indexed[0].source_id == "38912345"


def test_handle_message_drops_poison() -> None:
    repo = FakeRepo()
    asyncio.run(handle_message(repo, b"{not valid json"))
    assert repo.indexed == []


def test_repository_index_uses_doc_id() -> None:
    calls: list[dict] = []

    class FakeClient:
        async def index(self, **kwargs: object) -> None:
            calls.append(kwargs)

    repo = ArticleRepository(FakeClient())  # type: ignore[arg-type]
    article = enrich(Article.model_validate(SAMPLE))
    asyncio.run(repo.index(article))

    assert calls[0]["id"] == article.doc_id
    assert calls[0]["index"] == "articles"
    doc = calls[0]["document"]
    assert doc["lang"] == "en"
    assert isinstance(doc["published_at"], str)  # json mode
