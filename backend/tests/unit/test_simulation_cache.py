"""Testes do `SimulationResultCache`."""
from __future__ import annotations

import uuid

import pytest
from fakeredis import aioredis as fake_aioredis

from app.cache.simulation_cache import SimulationResultCache
from app.simulation.dto import MonteCarloSimulationResult


@pytest.fixture
async def redis_client():
    client = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def cache(redis_client) -> SimulationResultCache:
    return SimulationResultCache(redis_client, ttl_seconds=3600)


def _sample_result() -> MonteCarloSimulationResult:
    return MonteCarloSimulationResult(
        player1_win_probability=0.6123,
        confidence_interval_lower=0.60,
        confidence_interval_upper=0.62,
        sets_won_distribution={"2-0": 0.5, "2-1": 0.3, "0-2": 0.1, "1-2": 0.1},
        avg_match_duration_minutes=95.5,
        iterations=50_000,
    )


async def test_get_on_cache_miss_returns_none(cache: SimulationResultCache) -> None:
    key = SimulationResultCache.build_key(
        player1_id=uuid.uuid4(), player2_id=uuid.uuid4(), surface_id=1, best_of=3, iterations=1000
    )

    assert await cache.get(key) is None


async def test_set_then_get_round_trips_result(cache: SimulationResultCache) -> None:
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    key = SimulationResultCache.build_key(
        player1_id=p1, player2_id=p2, surface_id=2, best_of=5, iterations=100_000
    )
    result = _sample_result()

    await cache.set(key, result)
    retrieved = await cache.get(key)

    assert retrieved == result


async def test_build_key_is_symmetric_regardless_of_player_order(
    cache: SimulationResultCache,
) -> None:
    p1, p2 = uuid.uuid4(), uuid.uuid4()

    key_forward = SimulationResultCache.build_key(
        player1_id=p1, player2_id=p2, surface_id=1, best_of=3, iterations=1000
    )
    key_backward = SimulationResultCache.build_key(
        player1_id=p2, player2_id=p1, surface_id=1, best_of=3, iterations=1000
    )

    assert key_forward == key_backward


async def test_build_key_differs_for_different_parameters(cache: SimulationResultCache) -> None:
    p1, p2 = uuid.uuid4(), uuid.uuid4()

    base = SimulationResultCache.build_key(
        player1_id=p1, player2_id=p2, surface_id=1, best_of=3, iterations=1000
    )
    different_surface = SimulationResultCache.build_key(
        player1_id=p1, player2_id=p2, surface_id=2, best_of=3, iterations=1000
    )
    different_iterations = SimulationResultCache.build_key(
        player1_id=p1, player2_id=p2, surface_id=1, best_of=3, iterations=5000
    )

    assert base != different_surface
    assert base != different_iterations


async def test_corrupted_payload_treated_as_cache_miss(
    cache: SimulationResultCache, redis_client
) -> None:
    key = "corrupted-key"
    await redis_client.set(f"simcache:{key}", "not-valid-json{", ex=60)

    assert await cache.get(key) is None


async def test_set_applies_configured_ttl(redis_client) -> None:
    cache = SimulationResultCache(redis_client, ttl_seconds=120)
    key = SimulationResultCache.build_key(
        player1_id=uuid.uuid4(), player2_id=uuid.uuid4(), surface_id=1, best_of=3, iterations=1000
    )

    await cache.set(key, _sample_result())

    ttl = await redis_client.ttl(f"simcache:{key}")
    assert 0 < ttl <= 120


async def test_fails_open_on_get_when_redis_unavailable() -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    class _BrokenRedis:
        async def get(self, key: str):  # noqa: ARG002
            raise RedisConnectionError("Redis indisponível.")

    broken_cache = SimulationResultCache(_BrokenRedis())  # type: ignore[arg-type]
    result = await broken_cache.get("any-key")

    assert result is None


async def test_fails_open_on_set_when_redis_unavailable() -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    class _BrokenRedis:
        async def set(self, *args, **kwargs):  # noqa: ARG002
            raise RedisConnectionError("Redis indisponível.")

    broken_cache = SimulationResultCache(_BrokenRedis())  # type: ignore[arg-type]
    # Não deve levantar exceção — falha silenciosamente (fail-open).
    await broken_cache.set("any-key", _sample_result())
