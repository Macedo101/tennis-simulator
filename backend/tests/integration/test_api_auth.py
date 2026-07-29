"""Testes de integração do router de autenticação (`/api/v1/auth`)."""
from __future__ import annotations

from httpx import AsyncClient


async def _register(api_client: AsyncClient, email: str = "joao@example.com") -> dict:
    response = await api_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SenhaForte123!", "full_name": "João Macedo"},
    )
    return response


async def test_register_returns_201_and_user_without_password(api_client: AsyncClient) -> None:
    response = await _register(api_client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "joao@example.com"
    # Primeiro utilizador registado numa BD nova torna-se admin
    # automaticamente (ver AuthService.register, Módulo 6/interface web).
    assert body["role"] == "admin"
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_duplicate_email_returns_409(api_client: AsyncClient) -> None:
    await _register(api_client)
    response = await _register(api_client)

    assert response.status_code == 409


async def test_register_rejects_weak_password_missing_uppercase(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "semmaiuscula1", "full_name": "X"},
    )

    assert response.status_code == 422


async def test_register_rejects_weak_password_missing_number(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "SemNumeroAqui", "full_name": "X"},
    )

    assert response.status_code == 422


async def test_register_rejects_short_password(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "Ab1", "full_name": "X"},
    )

    assert response.status_code == 422


async def test_login_with_correct_credentials_returns_tokens(api_client: AsyncClient) -> None:
    await _register(api_client)

    response = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "joao@example.com", "password": "SenhaForte123!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_with_wrong_password_returns_401(api_client: AsyncClient) -> None:
    await _register(api_client)

    response = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "joao@example.com", "password": "PasswordErrada!"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_refresh_rotates_tokens(api_client: AsyncClient) -> None:
    await _register(api_client)
    login_response = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "joao@example.com", "password": "SenhaForte123!"},
    )
    original_refresh_token = login_response.json()["refresh_token"]

    refresh_response = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original_refresh_token}
    )

    assert refresh_response.status_code == 200
    new_refresh_token = refresh_response.json()["refresh_token"]
    assert new_refresh_token != original_refresh_token

    # o token original já não pode ser reutilizado
    reuse_response = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original_refresh_token}
    )
    assert reuse_response.status_code == 401


async def test_logout_revokes_refresh_token(api_client: AsyncClient) -> None:
    await _register(api_client)
    login_response = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "joao@example.com", "password": "SenhaForte123!"},
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = await api_client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh_token}
    )
    assert logout_response.status_code == 204

    reuse_response = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert reuse_response.status_code == 401


async def test_get_me_with_valid_token(api_client: AsyncClient) -> None:
    await _register(api_client)
    login_response = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "joao@example.com", "password": "SenhaForte123!"},
    )
    access_token = login_response.json()["access_token"]

    response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "joao@example.com"


async def test_get_me_without_token_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_get_me_with_invalid_token_returns_401(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer token-invalido"}
    )

    assert response.status_code == 401
