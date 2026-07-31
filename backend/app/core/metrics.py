"""Métricas Prometheus de negócio.

Complementam as métricas HTTP genéricas do `prometheus-fastapi-
instrumentator` (latência/contagem por rota, ver `app/main.py`) — estas
medem coisas que uma métrica HTTP genérica não consegue captar: a
duração da simulação Monte Carlo em si (não do pedido HTTP, que
responde em milissegundos com `202`), a taxa de acerto da cache, etc.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

SIMULATION_DURATION_SECONDS = Histogram(
    "simulation_duration_seconds",
    "Duração da execução de uma simulação Monte Carlo (motor, não o pedido HTTP).",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

SIMULATIONS_TOTAL = Counter(
    "simulations_total",
    "Número total de simulações processadas, por estado final.",
    ["status"],
)

SIMULATION_CACHE_REQUESTS_TOTAL = Counter(
    "simulation_cache_requests_total",
    "Pedidos de simulação por resultado de cache (hit/miss).",
    ["result"],
)

PREDICTION_DURATION_SECONDS = Histogram(
    "ml_prediction_duration_seconds",
    "Duração de uma previsão do modelo ML (feature building + inferência).",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
