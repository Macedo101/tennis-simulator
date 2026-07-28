"""Schema de resposta de previsões (modelo ML)."""
from __future__ import annotations

import datetime
from uuid import UUID

from pydantic import BaseModel


class ModelRef(BaseModel):
    name: str
    version: str


class PredictionResponse(BaseModel):
    match_id: UUID
    model: ModelRef
    player1_win_probability: float
    predicted_at: datetime.datetime
