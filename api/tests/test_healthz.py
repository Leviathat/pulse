from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.es import ArticleSearch, build_search_query
from api.main import app, get_search


def test_healthz() -> None:
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_build_search_query_empty_is_match_all() -> None:
    assert build_search_query(None, None, None, None) == {"match_all": {}}


def test_build_search_query_full_text_and_filters() -> None:
    q = build_search_query(
        "fastapi",
        "hackernews",
        datetime(2026, 7, 1, tzinfo=timezone.utc),
        datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    bool_q = q["bool"]
    assert bool_q["must"][0]["multi_match"]["query"] == "fastapi"
    assert {"term": {"source": "hackernews"}} in bool_q["filter"]
    rng = next(f for f in bool_q["filter"] if "range" in f)["range"]["published_at"]
    assert rng["gte"].startswith("2026-07-01")
    assert rng["lte"].startswith("2026-07-31")


class FakeClient:
    """Stands in for AsyncElasticsearch; records the search call."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def search(self, **kwargs: object) -> dict:
        self.calls.append(kwargs)
        return {
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {"_id": "abc", "_source": {"title": "hello", "source": "hackernews"}}
                ],
            }
        }


def test_search_endpoint_shapes_results() -> None:
    fake = FakeClient()
    app.dependency_overrides[get_search] = lambda: ArticleSearch(fake)  # type: ignore[arg-type]
    try:
        client = TestClient(app)
        resp = client.get("/search", params={"q": "hello", "limit": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["results"][0]["id"] == "abc"
        assert body["results"][0]["title"] == "hello"
        assert fake.calls[0]["size"] == 5
        assert fake.calls[0]["from_"] == 0
    finally:
        app.dependency_overrides.clear()
