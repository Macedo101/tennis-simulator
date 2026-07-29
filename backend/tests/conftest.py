"""Fixtures partilhadas pela suite de testes.

Cada teste recebe uma base de dados SQLite em memória própria, criada
de raiz e destruída no fim — isolamento total entre testes sem
depender de transações/rollback (mais simples de raciocinar, e o custo
de recriar o schema em SQLite em memória é desprezável).
"""
from __future__ import annotations

import datetime
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - regista todos os modelos em Base.metadata
from app.db.base import Base
from app.models.lookup import Country, Surface
from app.models.player import Player


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(db_session: AsyncSession) -> AsyncSession:
    """Sessão com dados de referência mínimos (países, superfícies)."""
    db_session.add_all(
        [
            Country(iso_code="RS", name="Serbia"),
            Country(iso_code="ES", name="Spain"),
            Surface(id=1, name="hard"),
            Surface(id=2, name="clay"),
            Surface(id=3, name="grass"),
        ]
    )
    await db_session.flush()
    return db_session


@pytest.fixture
def make_player():
    """Factory de conveniência para criar instâncias de `Player` em testes."""

    def _make(
        first_name: str = "Novak",
        last_name: str = "Djokovic",
        country_iso: str = "RS",
        date_of_birth: datetime.date | None = datetime.date(1987, 5, 22),
    ) -> Player:
        return Player(
            first_name=first_name,
            last_name=last_name,
            country_iso=country_iso,
            date_of_birth=date_of_birth,
        )

    return _make
