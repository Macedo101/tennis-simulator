"""Tabelas de referência (lookup): países e superfícies.

Extraídas como tabelas próprias (em vez de CHECK inline em `players` /
`tournament_editions`) porque são reutilizadas por múltiplas entidades —
evita repetir a lista de valores válidos em vários sítios.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Country(Base):
    """País (ISO 3166-1 alpha-2)."""

    __tablename__ = "countries"

    iso_code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - apenas debug
        return f"Country(iso_code={self.iso_code!r}, name={self.name!r})"


class Surface(Base):
    """Superfície de jogo (hard, clay, grass, carpet)."""

    __tablename__ = "surfaces"
    __table_args__ = (
        CheckConstraint(
            "name IN ('hard', 'clay', 'grass', 'carpet')",
            name="surface_name_valid",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Surface(id={self.id}, name={self.name!r})"
