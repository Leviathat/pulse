"""Cache-aside helper over Redis, storing JSON values with a TTL."""

import json

from redis.asyncio import Redis


class Cache:
    def __init__(self, redis: Redis, ttl_seconds: int = 30) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def get(self, key: str) -> dict | None:
        raw = await self._redis.get(key)
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: dict) -> None:
        await self._redis.set(key, json.dumps(value), ex=self._ttl)
