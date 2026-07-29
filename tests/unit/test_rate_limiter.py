"""Testes do `RateLimiter` (sliding window log sobre Redis).

Usa `fakeredis` (cliente Redis assíncrono em memória) — testa a lógica
real do sliding window sem exigir um servidor Redis a correr.
"""
from __future__ import annotations

import asyncio

import pytest
from fakeredis import aioredis as fake_aioredis

from app.cache.rate_limiter import RateLimiter


@pytest.fixture
async def redis_client():
    client = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def limiter(redis_client) -> RateLimiter:
    return RateLimiter(redis_client)


async def test_allows_requests_within_limit(limiter: RateLimiter) -> None:
    for _ in range(5):
        result = await limiter.check("user:alice", limit=5, window_seconds=60)
        assert result.allowed is True

    assert result.remaining == 0


async def test_blocks_requests_beyond_limit(limiter: RateLimiter) -> None:
    for _ in range(5):
        await limiter.check("user:bob", limit=5, window_seconds=60)

    result = await limiter.check("user:bob", limit=5, window_seconds=60)

    assert result.allowed is False
    assert result.remaining == 0


async def test_different_keys_have_independent_limits(limiter: RateLimiter) -> None:
    for _ in range(5):
        await limiter.check("user:alice", limit=5, window_seconds=60)

    result = await limiter.check("user:carol", limit=5, window_seconds=60)

    assert result.allowed is True


async def test_remaining_decreases_as_requests_are_made(limiter: RateLimiter) -> None:
    first = await limiter.check("user:dave", limit=3, window_seconds=60)
    second = await limiter.check("user:dave", limit=3, window_seconds=60)
    third = await limiter.check("user:dave", limit=3, window_seconds=60)

    assert (first.remaining, second.remaining, third.remaining) == (2, 1, 0)


async def test_window_expiry_allows_requests_again(limiter: RateLimiter) -> None:
    for _ in range(2):
        await limiter.check("user:erin", limit=2, window_seconds=1)

    blocked = await limiter.check("user:erin", limit=2, window_seconds=1)
    assert blocked.allowed is False

    await asyncio.sleep(1.1)

    allowed_again = await limiter.check("user:erin", limit=2, window_seconds=1)
    assert allowed_again.allowed is True


async def test_reset_at_is_in_the_future(limiter: RateLimiter) -> None:
    import time

    result = await limiter.check("user:frank", limit=5, window_seconds=60)

    assert result.reset_at > time.time()


async def test_fails_open_when_redis_unavailable() -> None:
    """Se o Redis estiver indisponível, o limiter deve falhar aberto
    (permitir o pedido) em vez de derrubar a API inteira."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    class _BrokenRedis:
        def pipeline(self, transaction: bool = True):  # noqa: ARG002
            raise RedisConnectionError("Redis indisponível.")

    broken_limiter = RateLimiter(_BrokenRedis())  # type: ignore[arg-type]
    result = await broken_limiter.check("user:anyone", limit=1, window_seconds=60)

    assert result.allowed is True
