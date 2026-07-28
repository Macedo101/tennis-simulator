"""Serviço de autenticação: registo, login, rotação de refresh tokens.

Orquestra `UserRepository` e `RefreshTokenRepository` (Módulo 2/7) com
as primitivas de `app.core.security` (hashing, JWT). Nenhuma rota
manipula passwords, tokens ou hashes diretamente — só chama métodos
deste serviço.
"""
from __future__ import annotations

import datetime
import uuid

from app.core.config import get_settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db.base import utcnow
from app.models.auth import RefreshToken, User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.dto import TokenPair


class InvalidCredentialsError(Exception):
    """Levantada para credenciais inválidas, tokens expirados/revogados,
    ou qualquer falha de autenticação — nunca distingue na mensagem
    "email não existe" de "password errada" (evita enumeração de contas)."""


class InsufficientPermissionsError(Exception):
    """Levantada quando um utilizador autenticado não tem o `role` exigido.

    Distinta de `InvalidCredentialsError` porque mapeia para `403`
    (autenticado, mas sem permissão), não `401` (não autenticado) —
    a distinção definida na especificação da API REST, secção 11.
    """


class AuthService:
    """Lógica de negócio de autenticação e emissão/rotação de tokens."""

    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self._users = user_repository
        self._refresh_tokens = refresh_token_repository

    async def register(self, *, email: str, password: str, full_name: str) -> User:
        """Regista um novo utilizador.

        A unicidade do email é garantida pela constraint `uq_users_email`
        — uma tentativa de registo duplicado propaga `DuplicateEntityError`
        (levantada pelo `BaseRepository.add`, Módulo 2), traduzida a 409
        pelo exception handler global (Módulo 6).
        """
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role="user",
        )
        return await self._users.add(user)

    async def login(self, *, email: str, password: str) -> TokenPair:
        """Autentica por email/password e emite um novo par de tokens."""
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Email ou password incorretos.")
        return await self._issue_token_pair(user)

    async def refresh(self, raw_refresh_token: str) -> TokenPair:
        """Troca um refresh token válido por um novo par de tokens (rotação).

        O refresh token usado é sempre revogado, mesmo que a emissão do
        novo par falhe a meio — isto é deliberado: um refresh token só
        pode ser trocado uma vez, nunca reaproveitado após uma tentativa.
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await self._refresh_tokens.get_by_hash(token_hash)
        if stored is None or not stored.is_active:
            raise InvalidCredentialsError("Refresh token inválido, expirado ou já usado.")

        await self._refresh_tokens.revoke(stored)
        user = await self._users.get_by_id_or_raise(stored.user_id)
        return await self._issue_token_pair(user)

    async def logout(self, raw_refresh_token: str) -> None:
        """Revoga um refresh token. Idempotente: nunca falha se já estiver revogado."""
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await self._refresh_tokens.get_by_hash(token_hash)
        if stored is not None and stored.revoked_at is None:
            await self._refresh_tokens.revoke(stored)

    async def get_current_user(self, access_token: str) -> User:
        """Resolve o `User` autenticado a partir de um access token JWT."""
        try:
            payload = decode_access_token(access_token)
        except InvalidTokenError as exc:
            raise InvalidCredentialsError(str(exc)) from exc

        try:
            user_id = uuid.UUID(payload["sub"])
        except ValueError as exc:
            raise InvalidCredentialsError("Token com identificador de utilizador inválido.") from exc

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("O utilizador associado a este token já não existe.")
        return user

    async def _issue_token_pair(self, user: User) -> TokenPair:
        settings = get_settings()
        access_token = create_access_token(user_id=user.id, role=user.role)
        raw_refresh_token, token_hash = generate_refresh_token()
        expires_at = utcnow() + datetime.timedelta(days=settings.refresh_token_expire_days)

        await self._refresh_tokens.add(
            RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in=settings.access_token_expire_minutes * 60,
        )
