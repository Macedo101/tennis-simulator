"""Repositório de torneios e edições."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tournament import Tournament, TournamentEdition
from app.repositories.base import BaseRepository


class TournamentRepository(BaseRepository[Tournament]):
    """Operações de persistência específicas de `Tournament`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Tournament)

    async def get_by_name(self, name: str) -> Tournament | None:
        """Procura um torneio pelo nome exato (é `UNIQUE` na especificação)."""
        stmt = select(Tournament).where(Tournament.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_edition_by_id(self, edition_id: UUID) -> TournamentEdition | None:
        """Devolve uma edição de torneio pelo seu próprio ID."""
        return await self._session.get(TournamentEdition, edition_id)

    async def get_edition(
        self, tournament_id: UUID, year: int
    ) -> TournamentEdition | None:
        """Devolve a edição de um torneio num ano específico."""
        stmt = select(TournamentEdition).where(
            TournamentEdition.tournament_id == tournament_id,
            TournamentEdition.year == year,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_editions_by_surface(
        self, surface_id: int, *, limit: int = 20
    ) -> list[TournamentEdition]:
        """Lista edições de torneio numa superfície específica."""
        stmt = (
            select(TournamentEdition)
            .where(TournamentEdition.surface_id == surface_id)
            .order_by(TournamentEdition.start_date.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add_edition(self, edition: TournamentEdition) -> TournamentEdition:
        """Adiciona uma nova edição de torneio (flush, sem commit)."""
        self._session.add(edition)
        await self._session.flush()
        return edition
