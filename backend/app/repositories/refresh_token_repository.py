"""Repositório de refresh tokens."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.auth import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Operações de persistência específicas de `RefreshToken`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RefreshToken)

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Procura um refresh token pelo seu hash (nunca pelo valor em claro)."""
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, refresh_token: RefreshToken) -> None:
        """Marca um refresh token como revogado (rotação ou logout)."""
        refresh_token.revoked_at = utcnow()
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """Revoga todos os refresh tokens ativos de um utilizador.

        Usado em cenários de segurança (ex.: suspeita de comprometimento
        de conta) — não exposto ainda por nenhum endpoint neste módulo,
        mas disponível para uso futuro (ex.: endpoint admin de
        "terminar todas as sessões").
        """
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        result = await self._session.execute(stmt)
        now = utcnow()
        for token in result.scalars().all():
            token.revoked_at = now
        await self._session.flush()
