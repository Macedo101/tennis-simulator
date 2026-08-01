"""Schemas de resposta relacionados com jogos (matches)."""
from __future__ import annotations

import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PlayerRef(BaseModel):
    """Referência resumida a um jogador (id + nome), usada em respostas de jogo."""

    id: UUID
    name: str


class TournamentEditionRef(BaseModel):
    """Referência resumida à edição de torneio de um jogo."""

    tournament_name: str
    year: int
    surface: str = Field(examples=["grass"])


class MatchSetSchema(BaseModel):
    set_number: int
    player1_games: int
    player2_games: int


class MatchStatisticsSchema(BaseModel):
    aces: int | None
    double_faults: int | None
    first_serve_pct: float | None


class MatchDetailResponse(BaseModel):
    """Detalhe completo de um jogo: sets, jogadores e estatísticas."""

    id: UUID
    tournament_edition: TournamentEditionRef
    round: str
    player1: PlayerRef
    player2: PlayerRef
    winner_id: UUID | None
    best_of: int
    status: str
    sets: list[MatchSetSchema]
    statistics: dict[str, MatchStatisticsSchema] = Field(
        description="Estatísticas por jogador, indexadas por `player_id` (string)."
    )


class HeadToHeadMatchSummary(BaseModel):
    match_id: UUID
    match_date: datetime.date
    winner_id: UUID | None
    round: str


class HeadToHeadResponse(BaseModel):
    """Resumo de confrontos diretos entre dois jogadores."""

    player1_id: UUID
    player2_id: UUID
    player1_wins: int
    player2_wins: int
    total_matches: int
    last_meeting_date: datetime.date | None
    matches: list[HeadToHeadMatchSummary]
