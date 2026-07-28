"""Repositório de simulações."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.simulation import Simulation
from app.repositories.base import BaseRepository


class SimulationRepository(BaseRepository[Simulation]):
    """Operações de persistência e transições de estado de `Simulation`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Simulation)

    async def list_for_user(self, user_id: UUID, *, limit: int = 20) -> list[Simulation]:
        """Histórico de simulações de um utilizador, mais recente primeiro.

        Usa `limit` simples (não keyset) — o histórico de simulações de
        um único utilizador é, por natureza, uma coleção pequena e
        limitada pelo rate limit de simulações (10/hora); a paginação
        cursor-based do Módulo 6 justifica-se para coleções globais
        (jogadores, jogos), não aqui.
        """
        stmt = (
            select(Simulation)
            .where(Simulation.user_id == user_id)
            .order_by(Simulation.requested_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_running(self, simulation: Simulation) -> None:
        simulation.status = "running"
        await self._session.flush()

    async def mark_completed(
        self,
        simulation: Simulation,
        *,
        player1_win_probability: float,
        confidence_interval_lower: float,
        confidence_interval_upper: float,
        sets_won_distribution: dict[str, float],
        avg_match_duration_minutes: float,
    ) -> None:
        simulation.status = "completed"
        simulation.player1_win_probability = player1_win_probability
        simulation.confidence_interval_lower = confidence_interval_lower
        simulation.confidence_interval_upper = confidence_interval_upper
        simulation.sets_won_distribution = sets_won_distribution
        simulation.avg_match_duration_minutes = avg_match_duration_minutes
        simulation.completed_at = utcnow()
        await self._session.flush()

    async def mark_failed(self, simulation: Simulation, *, error_message: str) -> None:
        simulation.status = "failed"
        simulation.error_message = error_message[:500]
        simulation.completed_at = utcnow()
        await self._session.flush()
