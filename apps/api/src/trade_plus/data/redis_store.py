"""Redis hot cache — latest predictions, prices, and pipeline status."""

from __future__ import annotations

import orjson
import redis.asyncio as redis
import structlog

from trade_plus.core.config import RedisConfig

logger = structlog.get_logger()


class RedisStore:
    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        self._client = redis.Redis.from_url(
            self._config.url, decode_responses=False,
            socket_connect_timeout=5, socket_keepalive=True,
        )
        await self._client.ping()
        logger.info("redis_connected")

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("Redis not connected")
        return self._client

    async def health_check(self) -> bool:
        try:
            await self.client.ping()
            return True
        except Exception:
            return False

    # ── Price cache (per instrument, 60s TTL) ────────────────────

    async def set_price(self, instrument: str, data: dict) -> None:
        await self.client.set(f"price:{instrument}", orjson.dumps(data), ex=120)

    async def get_price(self, instrument: str) -> dict | None:
        raw = await self.client.get(f"price:{instrument}")
        return orjson.loads(raw) if raw else None

    async def get_all_prices(self) -> dict[str, dict]:
        keys = await self.client.keys("price:*")
        result = {}
        for key in keys:
            raw = await self.client.get(key)
            if raw:
                inst = key.decode().split(":", 1)[1]
                result[inst] = orjson.loads(raw)
        return result

    # ── Prediction cache (per instrument, 10min TTL) ─────────────

    async def set_prediction(self, instrument: str, data: dict) -> None:
        await self.client.set(f"pred:{instrument}", orjson.dumps(data), ex=700)

    async def get_prediction(self, instrument: str) -> dict | None:
        raw = await self.client.get(f"pred:{instrument}")
        return orjson.loads(raw) if raw else None

    async def get_all_predictions(self) -> dict[str, dict]:
        keys = await self.client.keys("pred:*")
        result = {}
        for key in keys:
            raw = await self.client.get(key)
            if raw:
                inst = key.decode().split(":", 1)[1]
                result[inst] = orjson.loads(raw)
        return result

    # ── Pipeline status ──────────────────────────────────────────

    async def set_pipeline_status(self, data: dict) -> None:
        await self.client.set("pipeline:status", orjson.dumps(data), ex=700)

    async def get_pipeline_status(self) -> dict | None:
        raw = await self.client.get("pipeline:status")
        return orjson.loads(raw) if raw else None

    # ── Rate limiting ────────────────────────────────────────────

    async def incr_order_count(self) -> int:
        key = "rate:orders_per_sec"
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, 1)
        return count
