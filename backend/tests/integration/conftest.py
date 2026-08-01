"""Fixtures dos testes de integração da API (`httpx.AsyncClient` sobre a app real)."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db_session
from app.main import app


@pytest_asyncio.fixture
async def api_client(seeded_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Cliente HTTP para a app FastAPI real, com a BD de teste injetada.

    Sobrepõe a dependency `get_db_session` para devolver sempre a mesma
    sessão de teste (SQLite em memória, já semeada com países/superfícies)
    — a app nunca chega a tocar numa BD real durante os testes.
    """

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield seeded_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
