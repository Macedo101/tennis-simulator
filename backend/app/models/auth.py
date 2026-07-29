"""Utilizadores e tokens de refresh (autenticação)."""
from __future__ import annotations

import datetime
import uuid as uuid_mod

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.player import GUID


class User(Base):
    """Conta de utilizador da API (registo, login, autorização por `role`)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="users_role_valid"),
    )

    id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid_mod.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=utcnow, server_default=func.now(), nullable=False
    )

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"User(id={self.id}, email={self.email!r}, role={self.role!r})"


class RefreshToken(Base):
    """Refresh token opaco, guardado apenas como hash (nunca em texto plano).

    A rotação (revogar o antigo, emitir um novo a cada `POST /auth/refresh`)
    é responsabilidade da camada de serviço (`AuthService`), não deste
    modelo — o modelo só representa o estado, não a política de rotação.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid_mod.uuid4
    )
    user_id: Mapped[uuid_mod.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=utcnow, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        """`True` se o token ainda não expirou nem foi revogado.

        Normaliza `expires_at` para timezone-aware (assumindo UTC) antes
        de comparar: o SQLite (usado em testes) não preserva `tzinfo` em
        colunas `DateTime` — um valor gravado como aware volta naive
        depois de um round-trip pela BD. O Postgres (produção, com
        `DateTime(timezone=True)`) devolve sempre aware, pelo que esta
        normalização é um no-op nesse caso.
        """
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.UTC)
        return self.revoked_at is None and utcnow() < expires_at

    def __repr__(self) -> str:  # pragma: no cover
        return f"RefreshToken(user_id={self.user_id}, revoked={self.revoked_at is not None})"
