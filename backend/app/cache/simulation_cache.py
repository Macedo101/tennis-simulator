"""Cache de resultados de simulação Monte Carlo.

Motivação (já presente na stack tecnológica original): simulações são
caras em CPU — cachear o resultado de um pedido idêntico recente
("Djokovic vs Alcaraz, relva, melhor de 5, 100k iterações") evita
recomputar milhões de iterações. A chave é sempre construída a partir
dos jogadores em ordem normalizada (menor UUID primeiro), para que o
pedido "A vs B" e "B vs A" partilhem o mesmo resultado em cache — a
simulação é simétrica nesses termos (só os campos de resultado
diferem consoante quem é "jogador 1" na resposta, tratado pelo
chamador, não pelo cache).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from uuid import UUID

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.simulation.dto import MonteCarloSimulationResult


class SimulationResultCache:
    """Cache Redis de resultados de simulação, com TTL curto."""

    def __init__(
        self, redis_client: redis.Redis, *, key_prefix: str = "simcache", ttl_seconds: int = 3600
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def build_key(
        *, player1_id: UUID, player2_id: UUID, surface_id: int, best_of: int, iterations: int
    ) -> str:
        """Constrói a chave de cache, normalizando a ordem dos jogadores."""
        low, high = sorted((str(player1_id), str(player2_id)))
        return f"{low}:{high}:{surface_id}:{best_of}:{iterations}"

    async def get(self, key: str) -> MonteCarloSimulationResult | None:
        """Devolve o resultado em cache, ou `None` (cache miss ou Redis em baixo).

        Fail-open: uma falha do Redis aqui é tratada como cache miss —
        a simulação corre normalmente, só perde-se a otimização de
        custo, nunca a correção do resultado.
        """
        full_key = f"{self._key_prefix}:{key}"
        try:
            raw = await self._redis.get(full_key)
        except RedisError:
            return None
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            return MonteCarloSimulationResult(**payload)
        except (json.JSONDecodeError, TypeError):
            # Payload corrompido/desatualizado — trata como miss, não
            # deixa uma exceção de parsing rebentar o pedido do cliente.
            return None

    async def set(self, key: str, result: MonteCarloSimulationResult) -> None:
        """Guarda um resultado em cache, com o TTL configurado."""
        full_key = f"{self._key_prefix}:{key}"
        payload = json.dumps(asdict(result))
        try:
            await self._redis.set(full_key, payload, ex=self._ttl_seconds)
        except RedisError:
            # Fail-open: se não conseguirmos guardar, o próximo pedido
            # idêntico simplesmente recalcula — não é um erro do pedido atual.
            return
