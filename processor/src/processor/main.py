"""Stage-0 stub: consume raw_articles and log. Real processing arrives in stage 1."""

import asyncio
import logging
import os
import signal

from aiokafka import AIOKafkaConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("processor")

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "raw_articles")
GROUP_ID = os.getenv("KAFKA_GROUP_ID", "pulse-processor")


async def run() -> None:
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_BROKERS,
        group_id=GROUP_ID,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    log.info("stub consumer started: topic=%s group=%s brokers=%s", TOPIC, GROUP_ID, KAFKA_BROKERS)
    try:
        async for msg in consumer:
            log.info("received: partition=%d offset=%d key=%r", msg.partition, msg.offset, msg.key)
            await consumer.commit()
    finally:
        await consumer.stop()
        log.info("consumer stopped")


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
