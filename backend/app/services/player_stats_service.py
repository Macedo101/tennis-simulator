"""Serviço de estatísticas de jogadores: forma recente, stats por
superfície e resumo de head-to-head.

Orquestra `PlayerRepository` e `MatchRepository` (Módulo 2) para
produzir interpretações de negócio dos dados — a lógica que decide
"o que é forma recente" ou "como se agregam estatísticas por
superfície" vive aqui, não nos repositórios (que só sabem ler/escrever
linhas) nem nos routers da API (que só devem traduzir HTTP).
"""
from __future__ import annotations

from uuid import UUID

from app.repositories.exceptions import EntityNotFoundError
from app.repositories.match_repository import MatchRepository
from app.repositories.player_repository import PlayerRepository
from app.services.dto import (
    HeadToHeadSummaryResult,
    RecentFormResult,
    SurfaceStatsResult,
)


class PlayerStatsService:
    """Calcula estatísticas derivadas sobre jogadores e confrontos."""

    def __init__(
        self,
        player_repository: PlayerRepository,
        match_repository: MatchRepository,
    ) -> None:
        self._players = player_repository
        self._matches = match_repository

    async def get_recent_form(
        self, player_id: UUID, *, n_matches: int = 10
    ) -> RecentFormResult:
        """Calcula a forma recente de um jogador nas últimas N partidas completas.

        Levanta `EntityNotFoundError` se o jogador não existir — decisão
        deliberada: um pedido de estatísticas sobre um jogador inexistente
        é um erro de negócio (404 na API), não um resultado vazio válido.
        """
        if await self._players.get_by_id(player_id) is None:
            raise EntityNotFoundError("Player", player_id)

        matches = await self._matches.list_for_player(
            player_id, status="completed", limit=n_matches
        )

        wins = sum(1 for m in matches if m.winner_id == player_id)
        losses = len(matches) - wins

        return RecentFormResult(
            player_id=player_id,
            matches_considered=len(matches),
            wins=wins,
            losses=losses,
        )

    async def get_surface_stats(
        self, player_id: UUID, surface_id: int
    ) -> SurfaceStatsResult:
        """Calcula estatísticas agregadas de um jogador numa superfície.

        Reproduz em Python a mesma lógica da vista materializada
        `player_surface_stats` da especificação de BD: vitórias, derrotas
        e médias de `first_serve_pct` / `first_serve_points_won_pct`
        sobre os jogos completos do jogador nessa superfície.
        """
        if await self._players.get_by_id(player_id) is None:
            raise EntityNotFoundError("Player", player_id)

        matches = await self._matches.list_for_player_on_surface(player_id, surface_id)

        wins = sum(1 for m in matches if m.winner_id == player_id)
        losses = len(matches) - wins

        first_serve_pcts: list[float] = []
        first_serve_won_pcts: list[float] = []
        second_serve_won_pcts: list[float] = []
        for match in matches:
            for stats in match.statistics:
                if stats.player_id != player_id:
                    continue
                if stats.first_serve_pct is not None:
                    first_serve_pcts.append(stats.first_serve_pct)
                if stats.first_serve_points_won_pct is not None:
                    first_serve_won_pcts.append(stats.first_serve_points_won_pct)
                if stats.second_serve_points_won_pct is not None:
                    second_serve_won_pcts.append(stats.second_serve_points_won_pct)

        return SurfaceStatsResult(
            player_id=player_id,
            surface_id=surface_id,
            wins=wins,
            losses=losses,
            avg_first_serve_pct=_avg(first_serve_pcts),
            avg_first_serve_points_won_pct=_avg(first_serve_won_pcts),
            avg_second_serve_points_won_pct=_avg(second_serve_won_pcts),
        )

    async def get_head_to_head_summary(
        self, player1_id: UUID, player2_id: UUID
    ) -> HeadToHeadSummaryResult:
        """Resume o histórico de confrontos diretos entre dois jogadores."""
        for pid in (player1_id, player2_id):
            if await self._players.get_by_id(pid) is None:
                raise EntityNotFoundError("Player", pid)

        matches = await self._matches.get_head_to_head(player1_id, player2_id)

        player1_wins = sum(1 for m in matches if m.winner_id == player1_id)
        player2_wins = sum(1 for m in matches if m.winner_id == player2_id)
        last_meeting_date = matches[0].match_date if matches else None

        return HeadToHeadSummaryResult(
            player1_id=player1_id,
            player2_id=player2_id,
            player1_wins=player1_wins,
            player2_wins=player2_wins,
            last_meeting_date=last_meeting_date,
            match_ids=tuple(m.id for m in matches),
        )


def _avg(values: list[float]) -> float | None:
    """Média simples de uma lista de valores, ou `None` se vazia.

    Devolve `None` (não `0.0`) quando não há dados — distinção
    importante: "0% de primeiros serviços" e "sem dados suficientes"
    são situações diferentes que o chamador (API/frontend) deve poder
    distinguir, em vez de um zero enganador.
    """
    if not values:
        return None
    return round(float(sum(values) / len(values)), 2)
