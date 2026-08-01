"""Testes do seed idempotente de dados de referência (`app/db/seed.py`)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.db.base import Base
from app.db.seed import seed_reference_data
from app.models.lookup import Country, Surface


async def _make_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(bind=engine, expire_on_commit=False)


async def test_seed_inserts_surfaces_and_countries() -> None:
    engine, factory = await _make_session_factory()
    with patch("app.db.seed.AsyncSessionFactory", factory):
        await seed_reference_data()

    async with factory() as session:
        surfaces = (await session.execute(select(Surface.name))).scalars().all()
        countries = (await session.execute(select(Country.iso_code))).scalars().all()

    assert {"hard", "clay", "grass"} <= set(surfaces)
    assert "PT" in countries
    await engine.dispose()


async def test_seed_is_idempotent_when_run_twice() -> None:
    engine, factory = await _make_session_factory()
    with patch("app.db.seed.AsyncSessionFactory", factory):
        await seed_reference_data()
        await seed_reference_data()  # segunda vez não deve rebentar nem duplicar

    async with factory() as session:
        surface_count = len((await session.execute(select(Surface.id))).scalars().all())

    assert surface_count == 3
    await engine.dispose()


async def test_seed_preserves_existing_rows() -> None:
    engine, factory = await _make_session_factory()
    async with factory() as session:
        session.add(Surface(id=99, name="carpet"))
        await session.commit()

    with patch("app.db.seed.AsyncSessionFactory", factory):
        await seed_reference_data()

    async with factory() as session:
        surfaces = (await session.execute(select(Surface))).scalars().all()

    ids = {s.id for s in surfaces}
    assert 99 in ids  # linha pré-existente não foi tocada
    assert {1, 2, 3} <= ids  # seed normal também correu
    await engine.dispose()


async def test_seed_never_raises_when_db_unavailable() -> None:
    broken_factory = AsyncMock(side_effect=RuntimeError("BD indisponível"))
    with patch("app.db.seed.AsyncSessionFactory", broken_factory):
        await seed_reference_data()  # não deve levantar
