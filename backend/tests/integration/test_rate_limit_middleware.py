"""Testes do `RateLimitMiddleware`, sobre uma mini-app Starlette isolada
(não a app real) — permite injetar um `RateLimiter` com `fakeredis` e
controlar os limites configurados, sem tocar na app de produção (cuja
instância de middleware já está ligada ao Redis real no arranque).
"""
from __future__ import annotations

import uuid

import pytest
from fakeredis import aioredis as fake_aioredis
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.cache.middleware import RateLimitMiddleware
from app.cache.rate_limiter import RateLimiter
from app.core.security import create_access_token


async def _echo(request):  # noqa: ANN001, ARG001
    return JSONResponse({"ok": True})


@pytest.fixture
async def rate_limited_client(monkeypatch):
    fake_redis = fake_aioredis.FakeRedis(decode_responses=True)
    rate_limiter = RateLimiter(fake_redis)

    # Limites baixos e determinísticos para o teste (não os 100/20 reais).
    from app.core.config import Settings

    test_settings = Settings(
        rate_limit_authenticated_per_minute=3, rate_limit_unauthenticated_per_minute=2
    )
    monkeypatch.setattr("app.cache.middleware.get_settings", lambda: test_settings)

    starlette_app = Starlette(routes=[Route("/echo", _echo)])
    starlette_app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

    transport = ASGITransport(app=starlette_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await fake_redis.flushall()
    await fake_redis.aclose()


async def test_unauthenticated_requests_within_limit_succeed(rate_limited_client) -> None:
    for _ in range(2):
        response = await rate_limited_client.get("/echo")
        assert response.status_code == 200


async def test_unauthenticated_requests_beyond_limit_return_429(rate_limited_client) -> None:
    for _ in range(2):
        await rate_limited_client.get("/echo")

    response = await rate_limited_client.get("/echo")

    assert response.status_code == 429
    assert response.json()["type"].endswith("rate-limit-exceeded")
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in response.headers


async def test_authenticated_requests_get_higher_limit(rate_limited_client) -> None:
    token = create_access_token(user_id=uuid.uuid4(), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    # Limite autenticado configurado para 3 (> 2 do anónimo).
    for _ in range(3):
        response = await rate_limited_client.get("/echo", headers=headers)
        assert response.status_code == 200

    response = await rate_limited_client.get("/echo", headers=headers)
    assert response.status_code == 429


async def test_rate_limit_headers_present_on_successful_response(rate_limited_client) -> None:
    response = await rate_limited_client.get("/echo")

    assert response.headers["X-RateLimit-Limit"] == "2"
    assert int(response.headers["X-RateLimit-Remaining"]) == 1
    assert "X-RateLimit-Reset" in response.headers


async def test_invalid_token_is_treated_as_anonymous(rate_limited_client) -> None:
    headers = {"Authorization": "Bearer not-a-real-token"}

    response = await rate_limited_client.get("/echo", headers=headers)

    # Limite anónimo (2), não o autenticado (3) — token inválido não
    # deve dar acesso ao limite mais alto.
    assert response.headers["X-RateLimit-Limit"] == "2"
