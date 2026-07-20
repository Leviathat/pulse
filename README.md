# Pulse

Real-time media monitoring pipeline. Create a **monitor** with keywords — Pulse continuously
ingests publications from open sources (Hacker News first), matches them against your monitors,
and serves a live feed, full-text search and a mentions-over-time chart.

> **Status: Stage 1** — end-to-end vertical slice is live: the Go ingestor polls
> Hacker News, publishes to Kafka, the Python processor enriches and indexes into
> ElasticSearch, and the API serves full-text `/search`. See [Roadmap](#roadmap).

## Architecture

```
[Sources: HN API / RSS]
        |
        v
+------------------+     Kafka topic:      +----------------------+
|  Ingestor (Go)   | --> raw_articles -->  |  Processor (Python)  |
|  poll/normalize  |                       |  match/dedup/enrich  |
+------------------+                       +----------+-----------+
                                                      |
                                                      v
                                            +------------------+
                        Redis (cache)  <--> |  ElasticSearch   |
                              |             +--------+---------+
                              |                      |
                              +-----> +--------------+---+
                                      |   API (FastAPI)  |
                                      +--------+---------+
                                               |
                                      +--------+---------+
                                      |   UI (React+TS)  |
                                      +------------------+
```

Key design decisions (idempotency via deterministic ES `_id`, manual offset commits,
cache-aside with TTL, match-on-write feeds) are documented in
[pulse-theory.md](pulse-theory.md); the full spec is in [pulse-tz.md](pulse-tz.md).

## Quickstart

Requires Docker.

```sh
docker compose up -d --build
```

| Service | URL |
|---|---|
| API (OpenAPI docs) | http://localhost:8000/docs |
| Ingestor health | http://localhost:8080/healthz |
| ElasticSearch | http://localhost:9200 |
| Kafka (host clients) | localhost:19092 |
| Redis | localhost:6379 |
| Kibana (optional: `--profile debug`) | http://localhost:5601 |

### Try it

On startup the ingestor backfills the newest Hacker News stories and then polls
for new ones every 15s. After a few seconds there is data to query:

```sh
# how many articles have been indexed so far
curl localhost:9200/articles/_count

# full-text search over the archive, newest first
curl 'localhost:8000/search?q=python&limit=5'
curl 'localhost:8000/search?source=hackernews&limit=3'

# ingestor throughput / errors (Prometheus format)
curl -s localhost:8080/metrics | grep pulse_
```

`/search` accepts `q`, `source`, `from`, `to` (ISO-8601), `limit` and `offset`;
see the OpenAPI docs at http://localhost:8000/docs.

## Stack

| Layer | Tech |
|---|---|
| Ingest | Go, Gin, kafka-go |
| Bus | Apache Kafka (KRaft) |
| Processing | Python 3.12, aiokafka, Pydantic, Dishka |
| Storage / search | ElasticSearch |
| Cache | Redis |
| API | FastAPI |
| UI | React, TypeScript, Redux Toolkit |
| Infra | Docker, k3d + Helm, GitHub Actions → ghcr.io |
| Tests | pytest + testcontainers, go test |

## Repository layout

```
ingestor/    Go service: polls sources, normalizes, produces to Kafka
processor/   Python service: consumes, matches monitors, indexes into ES
api/         FastAPI service: monitors CRUD, feed, search, timeline
ui/          React dashboard
deploy/      k8s manifests / Helm charts
```

## Roadmap

- [x] **Stage 0** — monorepo, docker-compose (Kafka+ES+Redis), stub services, CI
- [x] **Stage 1** — vertical slice: HN → Kafka → processor → ES → `/search`
- [ ] **Stage 2** — monitors CRUD, feed, timeline, Redis cache (+ latency before/after)
- [ ] **Stage 3** — UI: monitors, feed, search, mentions chart
- [ ] **Stage 4** — k8s (k3d + Helm), metrics in README, polish

## Development

```sh
# Python lint + tests (per service: api/, processor/)
ruff check api processor
cd api && pip install -e ".[dev]" && pytest

# Go lint + tests
cd ingestor && go test ./... && golangci-lint run
```
