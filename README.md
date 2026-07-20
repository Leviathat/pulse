# Pulse

Real-time media monitoring pipeline. Create a **monitor** with keywords — Pulse continuously
ingests publications from open sources (Hacker News first), matches them against your monitors,
and serves a live feed, full-text search and a mentions-over-time chart.

> **Status: Stage 2** — the pipeline is live (Go ingestor → Kafka → Python
> processor → ElasticSearch → API) and now supports **monitors**: create a monitor
> with keywords, the processor tags matching articles on write, and the API serves
> a per-monitor `/feed`, a `/timeline` histogram (Redis cache-aside), and full-text
> `/search`. See [Roadmap](#roadmap).

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

# create a monitor; the processor tags matching articles as they arrive
MID=$(curl -s -X POST localhost:8000/monitors -H 'content-type: application/json' \
  -d '{"name":"Tech watch","keywords":["AI","python","kubernetes"]}' | jq -r .id)

curl localhost:8000/monitors                    # list monitors
curl "localhost:8000/monitors/$MID/feed"         # matched articles, newest first
curl "localhost:8000/monitors/$MID/timeline?interval=1h"  # mentions over time
curl -X DELETE "localhost:8000/monitors/$MID"    # 204

# ingestor throughput / errors (Prometheus format)
curl -s localhost:8080/metrics | grep pulse_
```

> Matching happens **on write**, so a new monitor tags articles ingested after it
> is created. To backfill the existing archive, reset the processor's consumer
> group to `--to-earliest` and restart it — reprocessing is idempotent
> (ES `_id = sha256(source:source_id)`), so no duplicates are created.

`/search` accepts `q`, `source`, `from`, `to` (ISO-8601), `limit` and `offset`;
`/timeline` accepts `interval` (e.g. `1h`, `1d`), `from` and `to`. See the OpenAPI
docs at http://localhost:8000/docs.

**Timeline caching.** `/timeline` is cached in Redis (cache-aside, 30 s TTL). On
the current dev dataset (24 matched docs) the p50 is ≈ 8 ms uncached vs ≈ 6 ms
served from cache — the cached path skips the ElasticSearch aggregation round-trip,
and the gap widens with data volume and histogram size.

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
- [x] **Stage 2** — monitors CRUD, match-on-write feed, timeline, Redis cache
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
