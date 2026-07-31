"""Torneios e respetivas edições anuais."""
from __future__ import annotations

import datetime
import uuid as uuid_mod

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.player import GUID


class Tournament(Base):
    """Identidade permanente de um torneio (ex.: 'Wimbledon').

    Separado de `TournamentEdition` porque atributos como superfície,
    cidade e prize money variam por ano — colapsar numa única tabela
    obrigaria a repetir o nome do torneio em cada edição, violando 2NF
    (dependência parcial do nome relativamente a apenas parte da chave
    composta torneio+ano).
    """

    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint(
            "category IN ('grand_slam', 'masters_1000', 'atp_500', 'atp_250', "
            "'challenger', 'itf')",
            name="tournaments_category_valid",
        ),
    )

    id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid_mod.uuid4
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=utcnow, server_default=func.now(), nullable=False
    )

    editions: Mapped[list[TournamentEdition]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Tournament(id={self.id}, name={self.name!r})"


class TournamentEdition(Base):
    """Instância anual de um torneio (superfície, piso, datas, prize money)."""

    __tablename__ = "tournament_editions"
    __table_args__ = (
        UniqueConstraint("tournament_id", "year", name="tournament_editions_unique"),
        CheckConstraint("year BETWEEN 1968 AND 2100", name="tournament_editions_year_range"),
        CheckConstraint(
            "draw_size IS NULL OR draw_size IN (16, 32, 64, 128)",
            name="tournament_editions_draw_size_valid",
        ),
        CheckConstraint("end_date >= start_date", name="tournament_editions_dates_order"),
        CheckConstraint(
            "prize_money_usd IS NULL OR prize_money_usd >= 0",
            name="tournament_editions_prize_non_negative",
        ),
    )

    id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid_mod.uuid4
    )
    tournament_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("tournaments.id", ondelete="RESTRICT"), nullable=False
    )
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    surface_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("surfaces.id"), nullable=False
    )
    country_iso: Mapped[str | None] = mapped_column(
        String(2), ForeignKey("countries.iso_code"), nullable=True
    )
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    draw_size: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    prize_money_usd: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    tournament: Mapped[Tournament] = relationship(back_populates="editions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"TournamentEdition(tournament_id={self.tournament_id}, year={self.year})"
