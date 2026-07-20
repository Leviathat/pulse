"""Unit tests for parsing, enrichment and the message handler."""

import asyncio
import json

from processor.config import Settings
from processor.enrich import detect_lang, enrich
from processor.es import ArticleRepository
from processor.main import handle_message
from processor.matching import Matcher
from processor.models import Article, EnrichedArticle, Monitor

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


def test_matcher_word_boundary_and_case_insensitive() -> None:
    matcher = Matcher(
        [
            Monitor(id="m1", name="py", keywords=["python", "fastapi"]),
            Monitor(id="m2", name="js", keywords=["java"]),
        ]
    )
    # "java" must not match inside "javascript" (word boundary).
    assert matcher.match("FastAPI is a Python framework") == ["m1"]
    assert matcher.match("I love JavaScript") == []
    assert matcher.match("Modern Java and Python") == ["m1", "m2"]
    assert matcher.match("nothing relevant here") == []


class FakeRepo:
    def __init__(self) -> None:
        self.indexed: list[EnrichedArticle] = []

    async def index(self, article: EnrichedArticle) -> None:
        self.indexed.append(article)


class StubCache:
    """Returns a fixed Matcher, standing in for the ES-backed MonitorCache."""

    def __init__(self, matcher: Matcher) -> None:
        self._matcher = matcher

    async def matcher(self) -> Matcher:
        return self._matcher


def test_handle_message_indexes_and_tags_matches() -> None:
    repo = FakeRepo()
    cache = StubCache(Matcher([Monitor(id="m1", keywords=["fastapi"])]))
    asyncio.run(handle_message(repo, cache, json.dumps(SAMPLE).encode()))
    assert len(repo.indexed) == 1
    assert repo.indexed[0].source_id == "38912345"
    assert repo.indexed[0].matched_monitor_ids == ["m1"]


def test_handle_message_no_match_leaves_empty_ids() -> None:
    repo = FakeRepo()
    cache = StubCache(Matcher([Monitor(id="m1", keywords=["kubernetes"])]))
    asyncio.run(handle_message(repo, cache, json.dumps(SAMPLE).encode()))
    assert repo.indexed[0].matched_monitor_ids == []


def test_handle_message_drops_poison() -> None:
    repo = FakeRepo()
    cache = StubCache(Matcher([]))
    asyncio.run(handle_message(repo, cache, b"{not valid json"))
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
