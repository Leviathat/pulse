# ТЗ: Real-Time Media Monitoring Pipeline

Рабочее название: **Pulse** (замени на своё)
Тип: pet-проект для портфолио (open source, публичный GitHub-репозиторий)
Цель: подтвердить на практике Go, Kafka, Kubernetes + публично воспроизвести профессиональные кейсы (поисковая оптимизация, Redis-кэширование, test coverage, CI/CD)

---

## 1. Описание продукта

Система мониторинга медиа-источников в реальном времени. Пользователь задаёт ключевые слова — система собирает упоминания из открытых источников, индексирует их и показывает на дашборде: лента совпадений, полнотекстовый поиск, график частоты упоминаний по времени.

Один пользовательский сценарий (MVP):
1. Пользователь создаёт "монитор" с ключевыми словами (например: `python`, `fastapi`).
2. Система непрерывно собирает новые публикации из подключённых источников.
3. Публикации, содержащие ключевые слова, появляются в ленте монитора.
4. Пользователь ищет по архиву собранного и смотрит график упоминаний.

---

## 2. Архитектура

```
[Sources: HN API / RSS / Reddit]
        |
        v
+------------------+     Kafka topic:      +----------------------+
|  Ingestor (Go)   | --> raw_articles -->  |  Processor (Python)  |
|  - fetch/poll    |                       |  - keyword matching  |
|  - normalize     |                       |  - dedup             |
|  - produce       |                       |  - enrich            |
+------------------+                       +----------+-----------+
        |                                             |
   /health /metrics                                   v
                                            +------------------+
                                            |  ElasticSearch   |
                                            |  (index+search)  |
                                            +--------+---------+
                                                     |
                                  +------------------+------------------+
                                  |                                     |
                                  v                                     v
                        +------------------+                  +------------------+
                        |  API (FastAPI)   | <-- Redis cache  |  Kibana (dev     |
                        |  REST endpoints  |                  |  only, optional) |
                        +--------+---------+                  +------------------+
                                 |
                                 v
                        +------------------+
                        |  UI (React+TS)   |
                        |  feed/search/    |
                        |  chart           |
                        +------------------+
```

Всё разворачивается в Kubernetes (k3d/minikube локально), деплой через GitHub Actions.

---

## 3. Компоненты

### 3.1 Ingestor (Go)

Назначение: сбор данных из источников и публикация нормализованных событий в Kafka.

Требования:
- Язык: Go 1.22+.
- HTTP-слой: Gin — endpoints `/healthz`, `/readyz`, `/metrics` (Prometheus-формат: счётчик собранных статей, ошибки по источникам, лаг последнего опроса).
- Kafka producer: `segmentio/kafka-go` или `confluent-kafka-go`.
- Источники MVP (в порядке приоритета):
  1. **Hacker News API** (https://github.com/HackerNews/API) — polling новых items раз в N секунд. Без ключей, стабильный, идеален для старта.
  2. **RSS-ленты** (конфигурируемый список URL) — парсинг через `mmcdole/gofeed`.
  3. (расширение) Reddit API — требует OAuth-app, добавлять после MVP.
- Нормализация в единый формат события (см. 4.1).
- Дедупликация на уровне ингестора не требуется (делает processor), но нужен `source_id` для идемпотентности.
- Конфигурация через env-переменные + YAML со списком источников.
- Graceful shutdown (обработка SIGTERM — важно для k8s).
- Unit-тесты на нормализацию и парсинг (цель coverage: 80%+).

### 3.2 Kafka

- Один брокер для MVP (Strimzi-оператор в k8s или bitnami helm chart; локально можно Redpanda — совместим по протоколу и легче).
- Топики:
  - `raw_articles` — сырые нормализованные события от ингестора. Партиций: 3. Retention: 24h.
  - `matched_articles` (расширение) — события после матчинга, если позже захочешь несколько консьюмеров.
- Ключ сообщения: `source_id` (для порядка внутри источника).

### 3.3 Processor (Python)

Назначение: консьюмит `raw_articles`, матчит по ключевым словам активных мониторов, пишет в ElasticSearch.

Требования:
- Python 3.12+, консьюмер: `aiokafka`.
- Матчинг MVP: case-insensitive поиск ключевых слов по `title + body` (простой substring/word-boundary). Расширение: percolate queries в ES.
- Дедупликация: по хэшу `source + source_id` (проверка существования в ES / Redis set).
- Обогащение: язык (`langdetect`), timestamp нормализация.
- Запись в ES: индекс `articles` (см. 4.2), bulk-запись батчами.
- Идемпотентность: повторная обработка того же события не создаёт дубликат (ES `_id` = хэш).
- DI через Dishka, конфиги через Pydantic Settings.
- Unit + интеграционные тесты (testcontainers для Kafka/ES). Цель coverage: 90%+ — это твоя резюме-метрика, меряй с первого дня.

### 3.4 API (Python, FastAPI)

Назначение: REST API для UI.

Endpoints (MVP):
- `POST /monitors` — создать монитор `{name, keywords: [string]}`.
- `GET /monitors` — список мониторов.
- `DELETE /monitors/{id}` — удалить.
- `GET /monitors/{id}/feed?limit&offset` — лента совпадений (из ES, сортировка по времени).
- `GET /search?q=&from=&to=&source=` — полнотекстовый поиск по архиву (ES query).
- `GET /monitors/{id}/timeline?interval=1h` — агрегация упоминаний по времени (ES date_histogram) для графика.
- `GET /healthz`, `GET /metrics`.

Требования:
- Хранение мониторов: для MVP достаточно ES-индекса `monitors` или Redis (не тащи PostgreSQL ради одной таблицы — меньше компонентов, легче деплой; если захочешь показать SQL — добавишь позже).
- **Redis-кэш**: результаты `timeline` и горячих `search`-запросов кэшируются с TTL 30–60 сек. Замерь и зафиксируй в README латентность с кэшем и без — это публичное воспроизведение твоего кейса «1–3 s → 100–230 ms».
- OpenAPI-схема из коробки (FastAPI) — укажи в README ссылку на `/docs`.
- Rate limiting не требуется (MVP).

### 3.5 UI (React + TypeScript)

Назначение: минимальный, но аккуратный дашборд.

Страницы (MVP — можно уместить в одну):
- Список мониторов + форма создания (название, ключевые слова через запятую).
- Лента совпадений выбранного монитора (карточки: заголовок-ссылка, источник, время, сниппет с подсветкой ключевого слова).
- Поисковая строка по архиву.
- График упоминаний (recharts, line/bar по данным `timeline`).

Требования:
- Vite + React 18 + TypeScript. Состояние: Redux Toolkit (подтверждает Redux из резюме) или RTK Query для API-слоя.
- Без UI-библиотек-монстров; Tailwind или простой CSS — дизайн вторичен, важна аккуратность.
- Сборка в статику, раздача через nginx-контейнер.

### 3.6 Инфраструктура

- **Kubernetes**: манифесты или Helm-chart в репо (`deploy/`). Компоненты: ingestor, processor, api, ui, redis, elasticsearch (single-node, dev-настройки), kafka/redpanda. Requests/limits проставлены. Probes: liveness+readiness у всех сервисов.
- Локальный запуск двух видов:
  1. `docker-compose up` — для быстрого старта любого, кто клонировал репо (обязателен!).
  2. `make k8s-up` — k3d/minikube + helm install (демонстрация k8s).
- **CI/CD (GitHub Actions)**:
  - PR: lint (ruff, golangci-lint, eslint) + tests + coverage report (badge в README).
  - main: build+push Docker-образов (ghcr.io), тег по SHA.
  - (расширение) авто-деплой в k8s на self-hosted/VPS.
- Секреты — только через env/GitHub Secrets, ничего в коде.

---

## 4. Модели данных

### 4.1 Событие `raw_articles` (Kafka, JSON)

```json
{
  "source": "hackernews",
  "source_id": "38912345",
  "url": "https://...",
  "title": "…",
  "body": "…",
  "author": "…",
  "published_at": "2026-07-03T10:00:00Z",
  "fetched_at": "2026-07-03T10:00:05Z"
}
```

### 4.2 Индекс `articles` (ElasticSearch)

- `_id`: sha256(source + ":" + source_id)
- Поля: все из события + `matched_monitor_ids: [string]`, `lang: keyword`
- Маппинг: `title`/`body` — `text` с анализатором `standard` (расширение: language-specific), остальное `keyword`/`date`.

---

## 5. Этапы (важно: вертикальные срезы, не слои)

**Этап 0 — скелет (1–2 вечера).** Monorepo, docker-compose с Kafka+ES+Redis, пустые сервисы с /healthz, CI с линтерами. Репо публичный с первого коммита.

**Этап 1 — вертикальный срез (1 неделя).** HN-ингестор → Kafka → processor → ES → один endpoint `/search` → curl. Ничего лишнего, но данные текут насквозь. Это самая важная веха: дальше проект уже «живой».

**Этап 2 — мониторы и лента (1 неделя).** CRUD мониторов, матчинг, `/feed`, `/timeline`, Redis-кэш + замеры латентности.

**Этап 3 — UI (1 неделя).** Дашборд: мониторы, лента, поиск, график.

**Этап 4 — k8s + полировка (3–5 вечеров).** Helm/манифесты, probes, README с архитектурной диаграммой, скриншотами, метриками (coverage, латентность, событий/сек), инструкцией запуска в 3 команды.

**Расширения (после MVP, по желанию):** Reddit/Telegram источники, percolate-матчинг, алерты (email/telegram-бот на aiogram — ещё один скилл из резюме), auth, Grafana-дашборд поверх /metrics.

---

## 6. Definition of Done (для резюме)

Проект готов попасть в резюме, когда:
- [ ] `docker-compose up` поднимает всё, и за 2 минуты видны живые данные в UI.
- [ ] Coverage processor+api ≥ 90%, badge в README.
- [ ] В README зафиксированы: пропускная способность ингестора (событий/сек), латентность поиска с Redis-кэшем и без (до/после).
- [ ] k8s-манифесты рабочие (видео/gif или скрин `kubectl get pods` в README).
- [ ] CI зелёный, образы публикуются в ghcr.io.

Буллеты для резюме получатся сами из чекбоксов выше — по нашей формуле «действие → механизм → цифра».

---

## 7. Технологический стек (сводно)

| Слой | Технологии |
|---|---|
| Ингест | Go, Gin, kafka-go, gofeed |
| Брокер | Kafka (или Redpanda) |
| Обработка | Python 3.12, aiokafka, Pydantic, Dishka |
| Хранение/поиск | ElasticSearch |
| Кэш | Redis |
| API | FastAPI |
| UI | React, TypeScript, Redux Toolkit, recharts |
| Инфра | Docker, Kubernetes (k3d), Helm, GitHub Actions, ghcr.io |
| Тесты | pytest + testcontainers, go test, coverage badges |
