"""Testes de integração do router de jogadores."""
from __future__ import annotations

import datetime
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import PlayerRanking


async def test_list_players_empty(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/players")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["pagination"]["has_more"] is False


async def test_list_players_returns_created_players(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    seeded_session.add_all(
        [
            make_player(first_name="Novak", last_name="Djokovic", country_iso="RS"),
            make_player(first_name="Carlos", last_name="Alcaraz", country_iso="ES"),
        ]
    )
    await seeded_session.flush()

    response = await api_client.get("/api/v1/players")

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    names = {item["last_name"] for item in body["data"]}
    assert names == {"Djokovic", "Alcaraz"}


async def test_list_players_pagination_respects_limit(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    for i in range(5):
        seeded_session.add(make_player(first_name=f"Player{i}", last_name="Test"))
    await seeded_session.flush()

    response = await api_client.get("/api/v1/players", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["has_more"] is True
    assert body["pagination"]["next_cursor"] is not None


async def test_list_players_second_page_via_cursor(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    for i in range(3):
        seeded_session.add(make_player(first_name=f"Player{i}", last_name="Test"))
    await seeded_session.flush()

    first_page = await api_client.get("/api/v1/players", params={"limit": 2})
    cursor = first_page.json()["pagination"]["next_cursor"]

    second_page = await api_client.get(
        "/api/v1/players", params={"limit": 2, "cursor": cursor}
    )

    assert second_page.status_code == 200
    body = second_page.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["has_more"] is False


async def test_list_players_invalid_cursor_returns_422(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/players", params={"cursor": "not-valid-base64!!"})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == 422


async def test_get_player_by_id(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    player = make_player(first_name="Novak", last_name="Djokovic")
    seeded_session.add(player)
    await seeded_session.flush()

    response = await api_client.get(f"/api/v1/players/{player.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Novak"
    assert body["id"] == str(player.id)


async def test_get_player_not_found_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/players/{uuid.uuid4()}")

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == 404
    assert body["type"].endswith("not-found")


async def test_get_player_rankings(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    player = make_player()
    seeded_session.add(player)
    await seeded_session.flush()
    seeded_session.add(
        PlayerRanking(
            player_id=player.id,
            ranking_date=datetime.date(2026, 7, 1),
            rank_position=1,
            points=9500,
        )
    )
    await seeded_session.flush()

    response = await api_client.get(f"/api/v1/players/{player.id}/rankings")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["rank_position"] == 1


async def test_get_player_recent_form_no_matches(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    player = make_player()
    seeded_session.add(player)
    await seeded_session.flush()

    response = await api_client.get(f"/api/v1/players/{player.id}/form")

    assert response.status_code == 200
    body = response.json()
    assert body["matches_considered"] == 0
    assert body["win_rate"] == 0.0


async def test_get_player_surface_stats_unknown_surface_returns_404(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    player = make_player()
    seeded_session.add(player)
    await seeded_session.flush()

    response = await api_client.get(f"/api/v1/players/{player.id}/stats/ice")

    assert response.status_code == 404
