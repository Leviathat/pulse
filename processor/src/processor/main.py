"""Consume raw_articles, enrich, and index into ElasticSearch.

Offsets are committed only after a successful index write (at-least-once), and
writes are idempotent via a deterministic doc_id, so reprocessing is safe.
"""

import asyncio
import logging
import signal

from aiokafka import AIOKafkaConsumer
from elasticsearch import AsyncElasticsearch
from pydantic import ValidationError

from processor.config import Settings
from processor.enrich import enrich
from processor.es import ArticleRepository
from processor.matching import MonitorCache, MonitorRepository
from processor.models import Article

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("processor")


async def run(settings: Settings | None = None) -> None:
    settings = settings or Settings()

    es = AsyncElasticsearch(settings.es_url)
    repo = ArticleRepository(es)
    monitors = MonitorCache(MonitorRepository(es))
    await repo.ensure_index()

    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_brokers,
        group_id=settings.kafka_group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    log.info(
        "consumer started: topic=%s group=%s brokers=%s",
        settings.kafka_topic,
        settings.kafka_group_id,
        settings.kafka_brokers,
    )
    try:
        async for msg in consumer:
            await handle_message(repo, monitors, msg.value)
            await consumer.commit()
    finally:
        await consumer.stop()
        await es.close()
        log.info("consumer stopped")


async def handle_message(
    repo: ArticleRepository, monitors: MonitorCache, raw: bytes
) -> None:
    """Parse, enrich, match and index one message. Poison messages are dropped."""
    try:
        article = Article.model_validate_json(raw)
    except ValidationError as exc:
        log.warning("dropping unparseable message: %s", exc)
        return
    enriched = enrich(article)
    matcher = await monitors.matcher()
    enriched.matched_monitor_ids = matcher.match(f"{article.title}\n{article.body}")
    await repo.index(enriched)
    log.info(
        "indexed %s (%s) matches=%s",
        article.doc_id[:12],
        article.title[:60],
        enriched.matched_monitor_ids,
    )


def main() -> None:
    loop = asyncio.new_event_loop()
    task = loop.create_task(run())
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        loop.run_until_complete(task)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
