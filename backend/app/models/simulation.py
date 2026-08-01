"""Pedido e resultado persistido de uma simulação Monte Carlo.

Ao contrário do motor de simulação (Módulo 4), que é uma função pura em
memória, este modelo representa o *pedido* como um recurso duradouro na
BD — necessário porque a simulação corre em background (Celery,
Módulo 8) e o cliente faz `GET /simulations/{id}` para saber o estado,
possivelmente muito depois de o worker ter terminado.
"""
from __future__ import annotations

import datetime
import uuid as uuid_mod

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow
from app.models.player import GUID


class Simulation(Base):
    """Um pedido de simulação Monte Carlo, com o seu estado e resultado.

    `status` modela uma máquina de estados simples:
    `queued -> running -> completed` (ou `failed`). Os campos de
    resultado (`player1_win_probability`, etc.) são `nullable` porque só
    existem depois de `completed` — nunca populados artificialmente
    enquanto o estado é `queued`/`running`.
    """

    __tablename__ = "simulations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="simulations_status_valid",
        ),
        CheckConstraint("best_of IN (3, 5)", name="simulations_best_of_valid"),
        CheckConstraint(
            "iterations BETWEEN 1000 AND 1000000", name="simulations_iterations_range"
        ),
        CheckConstraint("player1_id <> player2_id", name="simulations_distinct_players"),
    )

    id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid_mod.uuid4
    )
    user_id: Mapped[uuid_mod.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    player1_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("players.id"), nullable=False
    )
    player2_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("players.id"), nullable=False
    )
    surface_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("surfaces.id"), nullable=False
    )
    best_of: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")

    # -- Resultado (preenchido só quando status == 'completed') --
    player1_win_probability: Mapped[float | None] = mapped_column(nullable=True)
    confidence_interval_lower: Mapped[float | None] = mapped_column(nullable=True)
    confidence_interval_upper: Mapped[float | None] = mapped_column(nullable=True)
    sets_won_distribution: Mapped[dict[str, float] | None] = mapped_column(
        JSON, nullable=True
    )
    avg_match_duration_minutes: Mapped[float | None] = mapped_column(nullable=True)

    # -- Diagnóstico (preenchido só quando status == 'failed') --
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    requested_at: Mapped[datetime.datetime] = mapped_column(default=utcnow, nullable=False)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Simulation(id={self.id}, status={self.status!r})"
