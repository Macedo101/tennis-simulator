"""Primitivas de segurança: hashing de passwords e tokens JWT.

Nota sobre bcrypt: a stack tecnológica original previa `passlib[bcrypt]`.
Na prática, `passlib` (última versão estável, 1.7.4) é incompatível com
`bcrypt>=4.1` — a camada de compatibilidade do passlib assume atributos
(`__about__.__version__`) que a biblioteca `bcrypt` removeu, causando
falhas em runtime (`ValueError` no hashing). Uso a biblioteca `bcrypt`
diretamente: é mais simples, ativamente mantida, e elimina uma camada
de abstração hoje desnecessária (só faria sentido se precisássemos de
suportar múltiplos algoritmos de hash simultaneamente).
"""
from __future__ import annotations

import datetime
import hashlib
import secrets
import uuid
from typing import Any, TypedDict

import bcrypt
import jwt

from app.core.config import get_settings

#: bcrypt trunca (e levanta erro nalgumas versões) para passwords > 72
#: bytes — limite documentado do próprio algoritmo, não uma limitação
#: nossa. Validamos isto explicitamente em vez de deixar bcrypt falhar
#: com um erro pouco claro.
_BCRYPT_MAX_PASSWORD_BYTES = 72


class InvalidTokenError(Exception):
    """Levantada quando um JWT é inválido, malformado ou expirado."""


class AccessTokenPayload(TypedDict):
    sub: str
    role: str
    exp: int
    jti: str


def hash_password(plain_password: str) -> str:
    """Faz hash de uma password com bcrypt (salt gerado automaticamente)."""
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > _BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"A password não pode exceder {_BCRYPT_MAX_PASSWORD_BYTES} bytes."
        )
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica uma password em texto plano contra o seu hash bcrypt."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        # Hash malformado/vazio — nunca deve ser tratado como "password
        # correta"; falha fechada (fail-closed).
        return False


def create_access_token(*, user_id: uuid.UUID, role: str) -> str:
    """Cria um access token JWT assinado (HS256), com expiração curta.

    Contém `sub` (ID do utilizador), `role` (para autorização sem
    round-trip à BD), `exp` e `jti` (identificador único do token) —
    exatamente os claims especificados na API REST.
    """
    settings = get_settings()
    now = datetime.datetime.now(datetime.UTC)
    expires_at = now + datetime.timedelta(minutes=settings.access_token_expire_minutes)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "exp": expires_at,
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> AccessTokenPayload:
    """Decodifica e valida um access token JWT.

    Levanta `InvalidTokenError` para qualquer falha (assinatura
    inválida, expirado, malformado) — nunca deixa exceções da
    biblioteca `PyJWT` escapar para as camadas superiores.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Token inválido ou expirado.") from exc

    try:
        return AccessTokenPayload(
            sub=payload["sub"], role=payload["role"], exp=payload["exp"], jti=payload["jti"]
        )
    except KeyError as exc:
        raise InvalidTokenError("Token não contém os claims esperados.") from exc


def generate_refresh_token() -> tuple[str, str]:
    """Gera um novo refresh token opaco.

    Returns
    -------
    (raw_token, token_hash):
        `raw_token` é devolvido ao cliente uma única vez (nunca
        persistido). `token_hash` (SHA-256) é o que se guarda em
        `refresh_tokens.token_hash` — ver justificação na docstring do
        modelo `RefreshToken`.
    """
    raw_token = secrets.token_urlsafe(48)
    return raw_token, hash_refresh_token(raw_token)


def hash_refresh_token(raw_token: str) -> str:
    """Hash determinístico (SHA-256) de um refresh token, para lookup em BD.

    Não usa bcrypt aqui: bcrypt é indicado para passwords (baixa
    entropia, precisa de custo computacional elevado para dificultar
    força bruta); um refresh token já é um segredo de alta entropia
    gerado por `secrets.token_urlsafe`, pelo que um hash rápido e
    determinístico (SHA-256) é suficiente e permite pesquisa direta por
    igualdade na BD (bcrypt, sendo salgado, não permitiria `WHERE
    token_hash = ?`).
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
