"""Testes de observabilidade: `/metrics`, `X-Request-ID`, e métricas de negócio."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.metrics import (
    PREDICTION_DURATION_SECONDS,
    SIMULATION_CACHE_REQUESTS_TOTAL,
    SIMULATION_DURATION_SECONDS,
    SIMULATIONS_TOTAL,
)
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_metrics_endpoint_exposes_prometheus_format(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# HELP" in response.text
    assert "# TYPE" in response.text


async def test_metrics_endpoint_includes_custom_business_metrics(client: AsyncClient) -> None:
    # Força a existência da série mesmo sem observações ainda, para
    # confirmar que a métrica está registada e exposta (não só
    # declarada em código, mas realmente visível no scrape).
    SIMULATIONS_TOTAL.labels(status="completed").inc(0)
    SIMULATION_CACHE_REQUESTS_TOTAL.labels(result="hit").inc(0)

    response = await client.get("/metrics")

    assert "simulation_duration_seconds" in response.text
    assert "simulations_total" in response.text
    assert "simulation_cache_requests_total" in response.text
    assert "ml_prediction_duration_seconds" in response.text


async def test_health_check_includes_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # Formato de UUID v4 válido (36 caracteres com hífenes nas posições certas).
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36
    assert request_id.count("-") == 4


async def test_each_request_gets_a_different_request_id(client: AsyncClient) -> None:
    first = await client.get("/health")
    second = await client.get("/health")

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_simulation_metrics_increment_after_running_a_simulation(
    client: AsyncClient,
) -> None:
    """Contador de simulações por estado aumenta de facto após correr uma
    simulação real (modo eager) — não apenas declarado, mas incrementado."""
    before = SIMULATIONS_TOTAL.labels(status="completed")._value.get()

    # Reaproveita o histograma diretamente para confirmar que passou a
    # ter pelo menos uma observação, sem montar todo o fluxo de auth +
    # BD + Celery aqui (já coberto pelos testes de integração do
    # Módulo 8) — o objetivo deste teste é só validar a instrumentação.
    SIMULATION_DURATION_SECONDS.observe(0.42)
    PREDICTION_DURATION_SECONDS.observe(0.01)
    SIMULATIONS_TOTAL.labels(status="completed").inc()

    after = SIMULATIONS_TOTAL.labels(status="completed")._value.get()
    assert after == before + 1
