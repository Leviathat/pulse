# Pulse

Real-time media monitoring pipeline. Create a **monitor** with keywords — Pulse continuously
ingests publications from open sources (Hacker News first), matches them against your monitors,
and serves a live feed, full-text search and a mentions-over-time chart.

> **Status: Stage 3** — full stack is live end to end (Go ingestor → Kafka →
> Python processor → ElasticSearch → API → **React dashboard**). Create a monitor
> with keywords; the processor tags matching articles on write; the dashboard at
> http://localhost:3000 shows the feed (with keyword highlighting), a mentions-over-
> time chart, and full-text search over the archive. See [Roadmap](#roadmap).

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
| **Dashboard (UI)** | http://localhost:3000 |
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
| Processing | Python 3.12, aiokafka, Pydantic (Settings) |
| Storage / search | ElasticSearch |
| Cache | Redis |
| API | FastAPI |
| UI | React, TypeScript, Redux Toolkit (RTK Query), recharts |
| Infra | Docker, Kubernetes (kustomize) + k3d, GitHub Actions → ghcr.io |
| Tests | pytest, go test, ruff, golangci-lint |

## Repository layout

```
ingestor/    Go service: polls sources, normalizes, produces to Kafka
processor/   Python service: consumes, matches monitors, indexes into ES
api/         FastAPI service: monitors CRUD, feed, search, timeline
ui/          React dashboard (Vite, nginx)
deploy/k8s/  Kubernetes manifests (kustomize)
```

## Kubernetes (k3d)

The same services run on Kubernetes via [kustomize](deploy/k8s) manifests — each
with liveness/readiness probes and resource requests/limits; ElasticSearch and
Kafka are `StatefulSet`s with `PersistentVolumeClaim`s, and a `Job` creates the
`raw_articles` topic. In-cluster, nginx proxies the dashboard's `/api` to the
`api` Service, so no config changes between compose and k8s.

```sh
make k8s-up       # k3d cluster + build/import images + kubectl apply -k
make k8s-status   # kubectl -n pulse get pods,svc
make k8s-down
make k8s-validate # render + client-validate manifests (no cluster needed)
```

`make k8s-up` maps the k3d load balancer to `:8081`; the dashboard is then at
`http://pulse.localhost:8081` (add `127.0.0.1 pulse.localhost` to `/etc/hosts`).

## Roadmap

- [x] **Stage 0** — monorepo, docker-compose (Kafka+ES+Redis), stub services, CI
- [x] **Stage 1** — vertical slice: HN → Kafka → processor → ES → `/search`
- [x] **Stage 2** — monitors CRUD, match-on-write feed, timeline, Redis cache
- [x] **Stage 3** — React+TS dashboard: monitors, feed, search, mentions chart
- [x] **Stage 4** — Kubernetes manifests (kustomize): probes, limits, StatefulSets, k3d Makefile

## Development

```sh
# Python lint + tests (per service: api/, processor/)
ruff check api processor
cd api && pip install -e ".[dev]" && pytest

# Go lint + tests
cd ingestor && go test ./... && golangci-lint run
```
