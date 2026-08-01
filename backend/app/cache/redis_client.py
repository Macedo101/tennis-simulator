"""Cliente Redis partilhado para cache e rate limiting.

Instância única por processo (padrão já usado para o engine SQLAlchemy
em `app/db/base.py`) — evita reabrir uma ligação por pedido, o que
seria um desperdício de recursos para operações tão frequentes como
verificar um rate limit.
"""
from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis

from app.core.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    """Devolve o cliente Redis (cache/rate-limit), em cache por processo."""
    settings = get_settings()
    return redis.from_url(settings.redis_cache_url, decode_responses=True)
