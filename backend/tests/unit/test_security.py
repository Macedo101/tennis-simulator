"""Testes de `app.core.security` (hashing de passwords e JWT)."""
from __future__ import annotations

import datetime
import uuid

import jwt
import pytest

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


def test_hash_password_produces_different_hash_each_time() -> None:
    """bcrypt gera um salt aleatório — o mesmo password produz hashes diferentes."""
    hash1 = hash_password("SenhaForte123!")
    hash2 = hash_password("SenhaForte123!")

    assert hash1 != hash2
    assert verify_password("SenhaForte123!", hash1)
    assert verify_password("SenhaForte123!", hash2)


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("SenhaForte123!")
    assert verify_password("PasswordErrada456!", hashed) is False


def test_verify_password_handles_malformed_hash_gracefully() -> None:
    """Um hash malformado nunca deve ser tratado como 'password correta' (fail-closed)."""
    assert verify_password("qualquer-coisa", "hash-invalido-nao-e-bcrypt") is False


def test_hash_password_rejects_passwords_over_72_bytes() -> None:
    too_long = "A1" + "x" * 100
    with pytest.raises(ValueError, match="72 bytes"):
        hash_password(too_long)


def test_create_and_decode_access_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, role="user")

    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["role"] == "user"
    assert "jti" in payload


def test_decode_access_token_rejects_tampered_signature() -> None:
    token = create_access_token(user_id=uuid.uuid4(), role="user")
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_decode_access_token_rejects_expired_token() -> None:
    settings = get_settings()
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1)
    expired_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "role": "user", "exp": past, "jti": str(uuid.uuid4())},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(expired_token)


def test_decode_access_token_rejects_token_missing_claims() -> None:
    settings = get_settings()
    incomplete_token = jwt.encode(
        {"sub": str(uuid.uuid4())},  # falta role/jti
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(incomplete_token)


def test_generate_refresh_token_returns_matching_hash() -> None:
    raw_token, token_hash = generate_refresh_token()

    assert token_hash == hash_refresh_token(raw_token)


def test_generate_refresh_token_is_unique_each_call() -> None:
    raw1, _ = generate_refresh_token()
    raw2, _ = generate_refresh_token()

    assert raw1 != raw2


def test_hash_refresh_token_is_deterministic() -> None:
    raw_token = "some-fixed-raw-token-value"
    assert hash_refresh_token(raw_token) == hash_refresh_token(raw_token)
