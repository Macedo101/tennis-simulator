"""Testes de `POST /api/v1/players` (admin) e `GET /api/v1/surfaces`."""
from __future__ import annotations

from httpx import AsyncClient


async def _register_and_login(api_client: AsyncClient, email: str) -> str:
    await api_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SenhaForte123!", "full_name": "Teste Utilizador"},
    )
    login = await api_client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SenhaForte123!"},
    )
    return login.json()["access_token"]


async def test_first_user_can_create_player(api_client: AsyncClient) -> None:
    # Primeiro utilizador registado nesta BD de teste -> torna-se admin.
    token = await _register_and_login(api_client, "admin@example.com")

    response = await api_client.post(
        "/api/v1/players",
        json={"first_name": "Novak", "last_name": "Djokovic", "country_iso": "RS"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "Novak"
    assert body["last_name"] == "Djokovic"
    assert body["id"] is not None


async def test_second_user_cannot_create_player(api_client: AsyncClient) -> None:
    await _register_and_login(api_client, "primeiro@example.com")
    second_token = await _register_and_login(api_client, "segundo@example.com")

    response = await api_client.post(
        "/api/v1/players",
        json={"first_name": "Carlos", "last_name": "Alcaraz"},
        headers={"Authorization": f"Bearer {second_token}"},
    )

    assert response.status_code == 403


async def test_create_player_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/players", json={"first_name": "Carlos", "last_name": "Alcaraz"}
    )

    assert response.status_code == 401


async def test_create_player_validates_required_fields(api_client: AsyncClient) -> None:
    token = await _register_and_login(api_client, "admin2@example.com")

    response = await api_client.post(
        "/api/v1/players",
        json={"first_name": "", "last_name": "Alcaraz"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_created_player_is_visible_in_listing(api_client: AsyncClient) -> None:
    token = await _register_and_login(api_client, "admin3@example.com")
    await api_client.post(
        "/api/v1/players",
        json={"first_name": "Iga", "last_name": "Swiatek", "country_iso": "PT"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await api_client.get("/api/v1/players", params={"search": "Swiatek"})

    assert response.status_code == 200
    names = [p["last_name"] for p in response.json()["data"]]
    assert "Swiatek" in names


async def test_list_surfaces_returns_seeded_surfaces(seeded_session, api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/surfaces")

    assert response.status_code == 200
    names = {s["name"] for s in response.json()}
    assert {"hard", "clay", "grass"} <= names
