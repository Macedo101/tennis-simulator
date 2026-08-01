"""Objetos de resultado (DTOs) da camada de serviços.

`frozen=True` torna estes objetos imutáveis depois de calculados — um
resultado de estatísticas não deve poder ser alterado após ser devolvido
ao chamador (router/outro serviço), o que eliminaria uma classe de bugs
de mutação acidental partilhada entre pedidos concorrentes.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RecentFormResult:
    """Forma recente de um jogador, numa janela das últimas N partidas."""

    player_id: UUID
    matches_considered: int
    wins: int
    losses: int

    @property
    def win_rate(self) -> float:
        """Taxa de vitórias na janela considerada (0.0 se não houver jogos)."""
        if self.matches_considered == 0:
            return 0.0
        return round(self.wins / self.matches_considered, 4)


@dataclass(frozen=True, slots=True)
class SurfaceStatsResult:
    """Estatísticas agregadas de um jogador numa superfície específica.

    Espelha a vista materializada `player_surface_stats` da especificação
    de BD, calculada aqui em Python a partir dos dados carregados via
    repositório (ver justificação arquitetural do Módulo 3).
    """

    player_id: UUID
    surface_id: int
    wins: int
    losses: int
    avg_first_serve_pct: float | None
    avg_first_serve_points_won_pct: float | None
    avg_second_serve_points_won_pct: float | None

    @property
    def matches_played(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        if self.matches_played == 0:
            return 0.0
        return round(self.wins / self.matches_played, 4)


@dataclass(frozen=True, slots=True)
class HeadToHeadSummaryResult:
    """Resumo do histórico de confrontos diretos entre dois jogadores."""

    player1_id: UUID
    player2_id: UUID
    player1_wins: int
    player2_wins: int
    last_meeting_date: datetime.date | None
    match_ids: tuple[UUID, ...] = field(default_factory=tuple)

    @property
    def total_matches(self) -> int:
        return self.player1_wins + self.player2_wins


@dataclass(frozen=True, slots=True)
class TokenPair:
    """Par de tokens emitido em login/refresh, conforme a especificação da API."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
