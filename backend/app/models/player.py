"""Jogadores e histórico de ranking."""
from __future__ import annotations

import datetime
import uuid as uuid_mod
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import CHAR, TypeDecorator

from app.db.base import Base, utcnow

if TYPE_CHECKING:
    pass


class GUID(TypeDecorator):
    """Tipo de coluna portável para UUID.

    Usa o tipo nativo UUID do PostgreSQL em produção, mas cai para
    CHAR(32) em SQLite (usado nos testes) — necessário porque SQLite
    não tem tipo UUID nativo. Mantém sempre `uuid.UUID` do lado Python.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid_mod.UUID):
            value = uuid_mod.UUID(value)
        return value.hex

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid_mod.UUID):
            return value
        return uuid_mod.UUID(value)


class Player(Base):
    """Jogador de ténis profissional."""

    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint(
            "first_name", "last_name", "date_of_birth", name="players_identity"
        ),
        CheckConstraint(
            "height_cm IS NULL OR height_cm BETWEEN 140 AND 230",
            name="players_height_range",
        ),
        CheckConstraint(
            "plays IS NULL OR plays IN ('right-handed', 'left-handed', 'ambidextrous')",
            name="players_plays_valid",
        ),
    )

    id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid_mod.uuid4
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    country_iso: Mapped[str | None] = mapped_column(
        String(2), ForeignKey("countries.iso_code"), nullable=True
    )
    height_cm: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    plays: Mapped[str | None] = mapped_column(String(20), nullable=True)
    turned_pro: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )

    rankings: Mapped[list[PlayerRanking]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Player(id={self.id}, name='{self.first_name} {self.last_name}')"


class PlayerRanking(Base):
    """Registo histórico de ranking de um jogador numa data específica.

    Nota de escala: a especificação de BD define esta tabela como
    hypertable TimescaleDB em produção (série temporal por natureza).
    Essa otimização é aplicada na migração Postgres, não ao nível do
    modelo ORM (SQLAlchemy não tem conhecimento de hypertables — a
    conversão é feita via `SELECT create_hypertable(...)` na migração).
    """

    __tablename__ = "player_rankings"
    __table_args__ = (
        UniqueConstraint("player_id", "ranking_date", name="player_rankings_unique"),
        CheckConstraint("rank_position > 0", name="player_rankings_rank_positive"),
        CheckConstraint("points >= 0", name="player_rankings_points_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    ranking_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)

    player: Mapped[Player] = relationship(back_populates="rankings")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"PlayerRanking(player_id={self.player_id}, "
            f"date={self.ranking_date}, rank={self.rank_position})"
        )
