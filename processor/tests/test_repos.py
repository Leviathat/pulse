"""Tests for ES-backed repositories, the monitor cache, and enrich fallbacks."""

import asyncio

import processor.enrich as enrich_mod
from langdetect import LangDetectException
from processor.enrich import detect_lang
from processor.es import ArticleRepository
from processor.matching import MonitorCache, MonitorRepository
from processor.models import Monitor


# --- MonitorRepository / MonitorCache ---------------------------------------

class FakeSearchES:
    def __init__(self, hits: list[dict]) -> None:
        self._hits = hits
        self.calls = 0

    async def search(self, **_: object) -> dict:
        self.calls += 1
        return {"hits": {"hits": self._hits}}


def test_monitor_repository_maps_hits_to_monitors() -> None:
    es = FakeSearchES([{"_id": "m1", "_source": {"name": "py", "keywords": ["python"]}}])
    repo = MonitorRepository(es)  # type: ignore[arg-type]
    monitors = asyncio.run(repo.list_active())
    assert monitors == [Monitor(id="m1", name="py", keywords=["python"])]


class RecordingRepo:
    def __init__(self, monitors: list[Monitor]) -> None:
        self.monitors = monitors
        self.calls = 0

    async def list_active(self) -> list[Monitor]:
        self.calls += 1
        return self.monitors


def test_monitor_cache_refreshes_then_serves_from_memory(monkeypatch) -> None:
    # Pin monotonic() small (< ttl) so the first load must fire on the "never
    # loaded" sentinel, not because uptime happens to exceed the TTL.
    import processor.matching as matching_mod

    monkeypatch.setattr(matching_mod.time, "monotonic", lambda: 5.0)

    repo = RecordingRepo([Monitor(id="m1", keywords=["python"])])
    cache = MonitorCache(repo, ttl=1000)  # type: ignore[arg-type]

    async def go() -> None:
        m1 = await cache.matcher()
        assert m1.match("I like python") == ["m1"]
        await cache.matcher()  # within TTL: no reload

    asyncio.run(go())
    assert repo.calls == 1


def test_monitor_cache_reloads_when_ttl_zero() -> None:
    repo = RecordingRepo([Monitor(id="m1", keywords=["go"])])
    cache = MonitorCache(repo, ttl=0)  # type: ignore[arg-type]
    asyncio.run(cache.matcher())
    asyncio.run(cache.matcher())
    assert repo.calls == 2


def test_monitor_cache_keeps_previous_matcher_on_error() -> None:
    class BoomRepo:
        async def list_active(self) -> list[Monitor]:
            raise RuntimeError("es down")

    cache = MonitorCache(BoomRepo(), ttl=0)  # type: ignore[arg-type]
    matcher = asyncio.run(cache.matcher())  # must not raise
    assert matcher.match("anything") == []


# --- ArticleRepository.ensure_index -----------------------------------------

class FakeIndices:
    def __init__(self, exists: bool, raise_first: bool = False) -> None:
        self._exists = exists
        self._raise_first = raise_first
        self.created = False
        self.exists_calls = 0

    async def exists(self, index: str) -> bool:
        self.exists_calls += 1
        if self._raise_first and self.exists_calls == 1:
            raise ConnectionError("not ready")
        return self._exists

    async def create(self, index: str, **_: object) -> None:
        self.created = True


class FakeIndexES:
    def __init__(self, indices: FakeIndices) -> None:
        self.indices = indices


def test_ensure_index_creates_when_missing() -> None:
    idx = FakeIndices(exists=False)
    repo = ArticleRepository(FakeIndexES(idx))  # type: ignore[arg-type]
    asyncio.run(repo.ensure_index())
    assert idx.created is True


def test_ensure_index_skips_when_present() -> None:
    idx = FakeIndices(exists=True)
    repo = ArticleRepository(FakeIndexES(idx))  # type: ignore[arg-type]
    asyncio.run(repo.ensure_index())
    assert idx.created is False


def test_ensure_index_retries_until_ready() -> None:
    idx = FakeIndices(exists=False, raise_first=True)
    repo = ArticleRepository(FakeIndexES(idx))  # type: ignore[arg-type]
    asyncio.run(repo.ensure_index(retries=3, delay=0))
    assert idx.created is True
    assert idx.exists_calls == 2  # first raised, second succeeded


def test_ensure_index_gives_up_after_retries() -> None:
    class AlwaysFails:
        indices = None

        def __init__(self) -> None:
            self.indices = self

        async def exists(self, index: str) -> bool:
            raise ConnectionError("never ready")

    repo = ArticleRepository(AlwaysFails())  # type: ignore[arg-type]
    try:
        asyncio.run(repo.ensure_index(retries=2, delay=0))
    except RuntimeError as exc:
        assert "unavailable" in str(exc)
    else:
        raise AssertionError("expected RuntimeError after retries")


# --- enrich fallback --------------------------------------------------------

def test_detect_lang_falls_back_on_detector_error(monkeypatch) -> None:
    def boom(_: str) -> str:
        raise LangDetectException(0, "no features")

    monkeypatch.setattr(enrich_mod, "detect", boom)
    assert detect_lang("some text that would otherwise detect") == "unknown"
