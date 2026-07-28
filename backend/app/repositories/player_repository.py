"""Repositório de jogadores."""
from __future__ import annotations

import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import Player, PlayerRanking
from app.repositories.base import BaseRepository


class PlayerRepository(BaseRepository[Player]):
    """Operações de persistência específicas de `Player`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Player)

    async def search_by_name(self, query: str, *, limit: int = 20) -> list[Player]:
        """Pesquisa jogadores por nome (substring, case-insensitive).

        Em produção (Postgres), a especificação de BD usa um índice GIN
        com `pg_trgm` sobre `first_name || ' ' || last_name` para
        pesquisa fuzzy performante. Este método usa `ILIKE`/`LIKE`
        portável entre dialetos ao nível do repositório; o índice trgm
        é uma otimização de execução aplicada na migração, transparente
        para quem chama este método.
        """
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Player)
            .where(
                (Player.first_name + " " + Player.last_name).ilike(pattern)
                if self._session.bind is not None
                and self._session.bind.dialect.name == "postgresql"
                else (Player.first_name + " " + Player.last_name).like(pattern)
            )
            .order_by(Player.last_name)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_paginated(
        self,
        *,
        limit: int,
        after_created_at: datetime.datetime | None = None,
        after_id: UUID | None = None,
        search: str | None = None,
        country_iso: str | None = None,
    ) -> list[Player]:
        """Lista jogadores com paginação keyset em `(created_at, id)`.

        Busca `limit + 1` linhas (não apenas `limit`) — o item extra
        permite ao chamador (router) determinar `has_more` sem uma
        segunda query de `COUNT`. Ordena por `(created_at, id)`
        ascendente para que a comparação `>` seja bem definida mesmo
        quando múltiplos jogadores partilham o mesmo `created_at`.
        """
        stmt = select(Player)
        if search is not None:
            pattern = f"%{search.lower()}%"
            name_expr = Player.first_name + " " + Player.last_name
            is_postgres = (
                self._session.bind is not None
                and self._session.bind.dialect.name == "postgresql"
            )
            stmt = stmt.where(name_expr.ilike(pattern) if is_postgres else name_expr.like(pattern))
        if country_iso is not None:
            stmt = stmt.where(Player.country_iso == country_iso)

        if after_created_at is not None and after_id is not None:
            stmt = stmt.where(
                or_(
                    Player.created_at > after_created_at,
                    and_(
                        Player.created_at == after_created_at,
                        Player.id > after_id,
                    ),
                )
            )

        stmt = stmt.order_by(Player.created_at.asc(), Player.id.asc()).limit(limit + 1)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_identity(
        self,
        first_name: str,
        last_name: str,
        date_of_birth: datetime.date | None,
    ) -> Player | None:
        """Procura um jogador pela tripla que define a sua identidade única.

        Espelha a constraint `uq_players_identity` da especificação de
        BD — usado antes de inserir um jogador importado, para detetar
        duplicados silenciosos vindos de fontes externas (ATP/WTA/scraping)
        sem depender apenas do `IntegrityError` da BD.
        """
        stmt = select(Player).where(
            Player.first_name == first_name,
            Player.last_name == last_name,
            Player.date_of_birth == date_of_birth,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_country(self, country_iso: str, *, limit: int = 20) -> list[Player]:
        """Lista jogadores de um país (código ISO-2)."""
        stmt = (
            select(Player)
            .where(Player.country_iso == country_iso)
            .order_by(Player.last_name)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_current_ranking(self, player_id: UUID) -> PlayerRanking | None:
        """Devolve o registo de ranking mais recente de um jogador."""
        stmt = (
            select(PlayerRanking)
            .where(PlayerRanking.player_id == player_id)
            .order_by(PlayerRanking.ranking_date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_ranking_history(
        self,
        player_id: UUID,
        *,
        since: datetime.date | None = None,
        limit: int = 100,
    ) -> list[PlayerRanking]:
        """Devolve o histórico de ranking de um jogador, mais recente primeiro."""
        stmt = select(PlayerRanking).where(PlayerRanking.player_id == player_id)
        if since is not None:
            stmt = stmt.where(PlayerRanking.ranking_date >= since)
        stmt = stmt.order_by(PlayerRanking.ranking_date.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
