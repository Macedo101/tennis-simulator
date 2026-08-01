"""Schemas de simulações Monte Carlo."""
from __future__ import annotations

import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SimulationCreateRequest(BaseModel):
    player1_id: UUID
    player2_id: UUID
    surface: str = Field(examples=["clay"])
    best_of: int = Field(examples=[5])
    iterations: int = Field(ge=1_000, le=1_000_000, examples=[100_000])

    @field_validator("best_of")
    @classmethod
    def validate_best_of(cls, value: int) -> int:
        if value not in (3, 5):
            raise ValueError("best_of deve ser 3 ou 5.")
        return value


class SimulationAcceptedResponse(BaseModel):
    """Resposta `202 Accepted` ao criar uma simulação (despacho assíncrono)."""

    id: UUID
    status: str
    requested_at: datetime.datetime
    poll_url: str
    websocket_url: str


class ConfidenceInterval(BaseModel):
    lower: float
    upper: float


class SimulationStatusResponse(BaseModel):
    """Estado (e resultado, quando `completed`) de uma simulação."""

    id: UUID
    status: str
    player1_win_probability: float | None = None
    confidence_interval: ConfidenceInterval | None = None
    sets_won_distribution: dict[str, float] | None = None
    avg_match_duration_minutes: float | None = None
    error_message: str | None = None
    completed_at: datetime.datetime | None = None
