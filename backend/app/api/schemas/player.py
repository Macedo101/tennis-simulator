"""Schemas de resposta relacionados com jogadores."""
from __future__ import annotations

import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlayerCreateRequest(BaseModel):
    """Corpo de `POST /api/v1/players` — endpoint [admin]."""

    first_name: str = Field(min_length=1, max_length=100, examples=["Novak"])
    last_name: str = Field(min_length=1, max_length=100, examples=["Djokovic"])
    date_of_birth: datetime.date | None = None
    country_iso: str | None = Field(default=None, min_length=2, max_length=2, examples=["RS"])
    height_cm: int | None = Field(default=None, ge=140, le=230)
    plays: str | None = Field(
        default=None, examples=["right-handed"], description="right-handed, left-handed ou ambidextrous"
    )
    turned_pro: int | None = None


class PlayerListItem(BaseModel):
    """Representação resumida de um jogador, usada em listagens."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str = Field(examples=["Novak"])
    last_name: str = Field(examples=["Djokovic"])
    country_iso: str | None = Field(default=None, examples=["RS"])
    plays: str | None = Field(default=None, examples=["right-handed"])


class PlayerDetail(BaseModel):
    """Representação completa de um jogador."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    date_of_birth: datetime.date | None
    country_iso: str | None
    height_cm: int | None
    plays: str | None
    turned_pro: int | None


class PlayerRankingItem(BaseModel):
    """Um registo histórico de ranking."""

    model_config = ConfigDict(from_attributes=True)

    ranking_date: datetime.date
    rank_position: int
    points: int


class RecentFormResponse(BaseModel):
    """Forma recente de um jogador (janela das últimas N partidas)."""

    player_id: UUID
    matches_considered: int
    wins: int
    losses: int
    win_rate: float = Field(description="Proporção de vitórias na janela considerada.")


class SurfaceStatsResponse(BaseModel):
    """Estatísticas agregadas de um jogador numa superfície específica."""

    player_id: UUID
    surface_id: int
    wins: int
    losses: int
    matches_played: int
    win_rate: float
    avg_first_serve_pct: float | None
    avg_first_serve_points_won_pct: float | None
