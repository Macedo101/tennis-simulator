"""Repositório de jogos (matches), incluindo consulta de head-to-head."""
from __future__ import annotations

import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.match import Match, MatchStatistics
from app.models.tournament import TournamentEdition
from app.repositories.base import BaseRepository


class MatchRepository(BaseRepository[Match]):
    """Operações de persistência específicas de `Match`.

    Também expõe consultas sobre `match_sets`/`match_statistics`, porque
    estas tabelas são sempre lidas em conjunto com o jogo — não faz
    sentido um repositório separado que ninguém invocaria isoladamente
    (ver justificação arquitetural na secção 1 da resposta).
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Match)

    async def get_with_details(self, match_id: UUID) -> Match | None:
        """Devolve um jogo com sets e estatísticas já carregados (eager load).

        Usa `selectinload` (não `joinedload`): para relações
        one-to-many como `sets`/`statistics`, `selectinload` evita o
        problema clássico de *fan-out* de um `JOIN` (linhas duplicadas
        do jogo, uma por cada set/estatística) ao emitir uma segunda
        query com `WHERE match_id IN (...)`, mais eficiente aqui do que
        um único JOIN largo.
        """
        stmt = (
            select(Match)
            .where(Match.id == match_id)
            .options(selectinload(Match.sets), selectinload(Match.statistics))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_head_to_head(
        self, player1_id: UUID, player2_id: UUID, *, limit: int = 50
    ) -> list[Match]:
        """Devolve o histórico de confrontos diretos entre dois jogadores.

        Usa `player_low_id`/`player_high_id` (ver `Match` no Módulo 1) em
        vez de `WHERE (p1=A AND p2=B) OR (p1=B AND p2=A)` — a normalização
        já feita nessas colunas permite que o Postgres utilize um único
        índice composto (`ix_matches_h2h`) independentemente da ordem em
        que os IDs são passados a este método.
        """
        low, high = sorted((player1_id, player2_id), key=str)
        stmt = (
            select(Match)
            .where(Match.player_low_id == low, Match.player_high_id == high)
            .order_by(Match.match_date.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_player(
        self,
        player_id: UUID,
        *,
        since: datetime.date | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Match]:
        """Lista jogos em que um jogador participou (como player1 ou player2)."""
        stmt = select(Match).where(
            or_(Match.player1_id == player_id, Match.player2_id == player_id)
        )
        if since is not None:
            stmt = stmt.where(Match.match_date >= since)
        if status is not None:
            stmt = stmt.where(Match.status == status)
        stmt = stmt.order_by(Match.match_date.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_player_on_surface(
        self, player_id: UUID, surface_id: int, *, limit: int = 200
    ) -> list[Match]:
        """Lista jogos completos de um jogador numa superfície, com estatísticas.

        Junta `matches` a `tournament_editions` para filtrar por
        `surface_id` (a superfície pertence à edição, não ao jogo — ver
        especificação de BD, secção 5). Usado pelo `PlayerStatsService`
        para calcular o equivalente Python da vista materializada
        `player_surface_stats`.
        """
        stmt = (
            select(Match)
            .join(TournamentEdition, Match.tournament_edition_id == TournamentEdition.id)
            .where(
                or_(Match.player1_id == player_id, Match.player2_id == player_id),
                TournamentEdition.surface_id == surface_id,
                Match.status == "completed",
            )
            .options(selectinload(Match.statistics))
            .order_by(Match.match_date.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def list_by_tournament_edition(self, tournament_edition_id: UUID) -> list[Match]:
        """Lista todos os jogos de uma edição de torneio específica."""
        stmt = (
            select(Match)
            .where(Match.tournament_edition_id == tournament_edition_id)
            .order_by(Match.match_date)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add_statistics(self, statistics: MatchStatistics) -> MatchStatistics:
        """Adiciona estatísticas de um jogador para um jogo (flush, sem commit)."""
        self._session.add(statistics)
        await self._session.flush()
        return statistics
