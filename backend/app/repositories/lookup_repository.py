"""Repositório de tabelas de referência (`countries`, `surfaces`).

Separado dos repositórios de agregados de negócio (Player/Match/
Tournament) porque estas são tabelas de lookup puras, sem lógica de
domínio própria — só leitura direta por chave.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lookup import Country, Surface


class LookupRepository:
    """Leitura de tabelas de referência (países, superfícies)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_surface(self, surface_id: int) -> Surface | None:
        return await self._session.get(Surface, surface_id)

    async def get_country(self, iso_code: str) -> Country | None:
        return await self._session.get(Country, iso_code)

    async def list_surfaces(self) -> list[Surface]:
        result = await self._session.execute(select(Surface).order_by(Surface.id))
        return list(result.scalars().all())
