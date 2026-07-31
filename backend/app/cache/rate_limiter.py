"""Rate limiting por sliding window log, sobre Redis.

Usa um sorted set por chave (`ratelimit:<key>`), com o timestamp de
cada pedido como score. Isto conta sempre os pedidos dos últimos N
segundos exatos (janela deslizante real), ao contrário de um contador
fixo por minuto (`INCR`+`EXPIRE`), que permite picos de 2x o limite na
fronteira entre duas janelas fixas consecutivas.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import redis.asyncio as redis
from redis.exceptions import RedisError


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Resultado de uma verificação de rate limit."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: int  #: timestamp UNIX em que a janela atual termina


class RateLimiter:
    """Sliding window log rate limiter."""

    def __init__(self, redis_client: redis.Redis, *, key_prefix: str = "ratelimit") -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix

    async def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        """Regista um pedido e verifica se ainda está dentro do limite.

        Fail-open: se o Redis estiver indisponível, a verificação
        assume-se permitida — um rate limiter não deve tornar-se, ele
        próprio, um ponto único de falha que derruba a API inteira
        quando o Redis está em baixo.
        """
        full_key = f"{self._key_prefix}:{key}"
        now = time.time()
        window_start = now - window_seconds
        reset_at = int(now) + window_seconds

        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(full_key, 0, window_start)
                pipe.zadd(full_key, {str(uuid.uuid4()): now})
                pipe.zcard(full_key)
                pipe.expire(full_key, window_seconds)
                results = await pipe.execute()
            count = int(results[2])
        except RedisError:
            return RateLimitResult(
                allowed=True, limit=limit, remaining=limit, reset_at=reset_at
            )

        allowed = count <= limit
        remaining = max(0, limit - count)
        return RateLimitResult(allowed=allowed, limit=limit, remaining=remaining, reset_at=reset_at)
