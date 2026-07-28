"""Testes do `AuthService`."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.exceptions import DuplicateEntityError
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService, InvalidCredentialsError


@pytest.fixture
def auth_service(db_session: AsyncSession) -> AuthService:
    return AuthService(UserRepository(db_session), RefreshTokenRepository(db_session))


async def test_register_creates_user_with_hashed_password(auth_service: AuthService) -> None:
    user = await auth_service.register(
        email="joao@example.com", password="SenhaForte123!", full_name="João Macedo"
    )

    assert user.id is not None
    assert user.email == "joao@example.com"
    assert user.role == "user"
    assert user.hashed_password != "SenhaForte123!"


async def test_register_duplicate_email_raises_duplicate_entity_error(
    auth_service: AuthService,
) -> None:
    await auth_service.register(
        email="joao@example.com", password="SenhaForte123!", full_name="João Macedo"
    )

    with pytest.raises(DuplicateEntityError):
        await auth_service.register(
            email="joao@example.com", password="OutraSenha456!", full_name="João Outro"
        )


async def test_login_with_correct_credentials_returns_token_pair(
    auth_service: AuthService,
) -> None:
    await auth_service.register(
        email="joao@example.com", password="SenhaForte123!", full_name="João Macedo"
    )

    tokens = await auth_service.login(email="joao@example.com", password="SenhaForte123!")

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"
    assert tokens.expires_in > 0


async def test_login_with_wrong_password_raises_invalid_credentials(
    auth_service: AuthService,
) -> None:
    await auth_service.register(
        email="joao@example.com", password="SenhaForte123!", full_name="João Macedo"
    )

    with pytest.raises(InvalidCredentialsError):
        await auth_service.login(email="joao@example.com", password="PasswordErrada!")


async def test_login_with_unknown_email_raises_invalid_credentials(
    auth_service: AuthService,
) -> None:
    with pytest.raises(InvalidCredentialsError):
        await auth_service.login(email="ninguem@example.com", password="SenhaForte123!")


async def test_refresh_rotates_token_and_invalidates_old_one(auth_service: AuthService) -> None:
    await auth_service.register(
        email="joao@example.com", password="SenhaForte123!", full_name="João Macedo"
    )
    original_tokens = await auth_service.login(
        email="joao@example.com", password="SenhaForte123!"
    )

    new_tokens = await auth_service.refresh(original_tokens.refresh_token)

    assert new_tokens.refresh_token != original_tokens.refresh_token
    # o refresh token original já não pode voltar a ser usado
    with pytest.raises(InvalidCredentialsError):
        await auth_service.refresh(original_tokens.refresh_token)


async def test_refresh_with_invalid_token_raises_invalid_credentials(
    auth_service: AuthService,
) -> None:
    with pytest.raises(InvalidCredentialsError):
        await auth_service.refresh("token-que-nunca-existiu")


async def test_logout_revokes_refresh_token(auth_service: AuthService) -> None:
    await auth_service.register(
        email="joao@example.com", password="SenhaForte123!", full_name="João Macedo"
    )
    tokens = await auth_service.login(email="joao@example.com", password="SenhaForte123!")

    await auth_service.logout(tokens.refresh_token)

    with pytest.raises(InvalidCredentialsError):
        await auth_service.refresh(tokens.refresh_token)


async def test_logout_is_idempotent_for_unknown_token(auth_service: AuthService) -> None:
    # Não deve levantar exceção mesmo para um token que nunca existiu.
    await auth_service.logout("token-inexistente")


async def test_get_current_user_with_valid_token(auth_service: AuthService) -> None:
    user = await auth_service.register(
        email="joao@example.com", password="SenhaForte123!", full_name="João Macedo"
    )
    tokens = await auth_service.login(email="joao@example.com", password="SenhaForte123!")

    resolved_user = await auth_service.get_current_user(tokens.access_token)

    assert resolved_user.id == user.id


async def test_get_current_user_with_invalid_token_raises(auth_service: AuthService) -> None:
    with pytest.raises(InvalidCredentialsError):
        await auth_service.get_current_user("token-invalido")
