"""Jogos, sets e estatísticas por jogo."""
from __future__ import annotations

import datetime
import uuid as uuid_mod

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.player import GUID


class Match(Base):
    """Um jogo entre dois jogadores, numa edição de torneio.

    `player_low_id` / `player_high_id` normalizam o par de jogadores
    independentemente da ordem em que `player1`/`player2` foram
    registados, permitindo indexar o confronto direto (H2H) com uma
    única lookup em vez de `WHERE (p1=A AND p2=B) OR (p1=B AND p2=A)`.

    Na especificação Postgres estas são colunas geradas
    (`GENERATED ALWAYS AS (...) STORED`), calculadas pelo próprio motor
    de BD. Ao nível do ORM, mantemo-las como colunas normais preenchidas
    por um event listener `before_insert`/`before_update` — isto garante
    o mesmo comportamento de forma portável entre PostgreSQL (produção)
    e SQLite (testes), onde `GENERATED ALWAYS AS` tem suporte limitado.
    A migração Alembic para Postgres usa a coluna gerada nativa como
    camada adicional de garantia ao nível da BD.
    """

    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint(
            "round IN ('R128', 'R64', 'R32', 'R16', 'QF', 'SF', 'F')",
            name="matches_round_valid",
        ),
        CheckConstraint("best_of IN (3, 5)", name="matches_best_of_valid"),
        CheckConstraint(
            "status IN ('scheduled', 'in_progress', 'completed', 'retired', 'walkover')",
            name="matches_status_valid",
        ),
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes > 0",
            name="matches_duration_positive",
        ),
        CheckConstraint("player1_id <> player2_id", name="matches_distinct_players"),
    )

    id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid_mod.uuid4
    )
    tournament_edition_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("tournament_editions.id", ondelete="CASCADE"), nullable=False
    )
    round: Mapped[str] = mapped_column(String(10), nullable=False)
    player1_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("players.id"), nullable=False
    )
    player2_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("players.id"), nullable=False
    )
    winner_id: Mapped[uuid_mod.UUID | None] = mapped_column(
        GUID, ForeignKey("players.id"), nullable=True
    )
    best_of: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    match_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scheduled"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )
    # Preenchidas pelo event listener abaixo (ver docstring da classe)
    player_low_id: Mapped[uuid_mod.UUID] = mapped_column(GUID, nullable=False)
    player_high_id: Mapped[uuid_mod.UUID] = mapped_column(GUID, nullable=False)

    sets: Mapped[list[MatchSet]] = relationship(
        back_populates="match", cascade="all, delete-orphan", order_by="MatchSet.set_number"
    )
    statistics: Mapped[list[MatchStatistics]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Match(id={self.id}, {self.player1_id} vs {self.player2_id})"


@event.listens_for(Match, "before_insert")
@event.listens_for(Match, "before_update")
def _set_normalized_player_pair(mapper, connection, target: Match) -> None:
    """Mantém player_low_id/player_high_id sincronizados com player1/player2.

    Ver docstring de `Match` para a justificação desta abordagem
    portável (em vez de coluna gerada nativa, usada apenas em Postgres).
    """
    if target.player1_id is None or target.player2_id is None:
        return
    low, high = sorted((target.player1_id, target.player2_id), key=str)
    target.player_low_id = low
    target.player_high_id = high


class MatchSet(Base):
    """Resultado de um set individual dentro de um jogo."""

    __tablename__ = "match_sets"
    __table_args__ = (
        UniqueConstraint("match_id", "set_number", name="match_sets_unique"),
        CheckConstraint("set_number BETWEEN 1 AND 5", name="match_sets_number_range"),
        CheckConstraint("player1_games >= 0", name="match_sets_p1_games_non_negative"),
        CheckConstraint("player2_games >= 0", name="match_sets_p2_games_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    set_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    player1_games: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    player2_games: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tiebreak_p1_points: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    tiebreak_p2_points: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    match: Mapped[Match] = relationship(back_populates="sets")

    def __repr__(self) -> str:  # pragma: no cover
        return f"MatchSet(match_id={self.match_id}, set={self.set_number})"


class MatchStatistics(Base):
    """Estatísticas de um jogador num jogo específico (uma linha por jogador)."""

    __tablename__ = "match_statistics"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="match_statistics_unique"),
        CheckConstraint("aces IS NULL OR aces >= 0", name="match_statistics_aces_non_negative"),
        CheckConstraint(
            "double_faults IS NULL OR double_faults >= 0",
            name="match_statistics_df_non_negative",
        ),
        CheckConstraint(
            "first_serve_pct IS NULL OR first_serve_pct BETWEEN 0 AND 100",
            name="match_statistics_first_serve_pct_range",
        ),
        CheckConstraint(
            "first_serve_points_won_pct IS NULL OR "
            "first_serve_points_won_pct BETWEEN 0 AND 100",
            name="match_statistics_fspw_range",
        ),
        CheckConstraint(
            "second_serve_points_won_pct IS NULL OR "
            "second_serve_points_won_pct BETWEEN 0 AND 100",
            name="match_statistics_sspw_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("players.id"), nullable=False
    )
    aces: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    double_faults: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    first_serve_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    first_serve_points_won_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    second_serve_points_won_pct: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    break_points_saved: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    break_points_faced: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    total_points_won: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    match: Mapped[Match] = relationship(back_populates="statistics")

    def __repr__(self) -> str:  # pragma: no cover
        return f"MatchStatistics(match_id={self.match_id}, player_id={self.player_id})"
