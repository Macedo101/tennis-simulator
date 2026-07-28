"""Testes de integração do router de jogos (`/api/v1/matches`)."""
from __future__ import annotations

import datetime
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, MatchSet, MatchStatistics
from app.models.tournament import Tournament, TournamentEdition


async def _seed_match(seeded_session: AsyncSession, make_player):
    player1 = make_player(first_name="Novak", last_name="Djokovic", country_iso="RS")
    player2 = make_player(first_name="Carlos", last_name="Alcaraz", country_iso="ES")
    seeded_session.add_all([player1, player2])
    await seeded_session.flush()

    tournament = Tournament(name="Wimbledon", category="grand_slam")
    seeded_session.add(tournament)
    await seeded_session.flush()

    edition = TournamentEdition(
        tournament_id=tournament.id,
        year=2025,
        surface_id=3,  # grass
        start_date=datetime.date(2025, 6, 30),
        end_date=datetime.date(2025, 7, 13),
    )
    seeded_session.add(edition)
    await seeded_session.flush()

    match = Match(
        tournament_edition_id=edition.id,
        round="F",
        player1_id=player1.id,
        player2_id=player2.id,
        winner_id=player1.id,
        best_of=5,
        match_date=datetime.date(2025, 7, 13),
        status="completed",
    )
    seeded_session.add(match)
    await seeded_session.flush()

    seeded_session.add(
        MatchSet(match_id=match.id, set_number=1, player1_games=6, player2_games=4)
    )
    seeded_session.add(
        MatchStatistics(match_id=match.id, player_id=player1.id, aces=12, double_faults=2)
    )
    await seeded_session.flush()

    return player1, player2, match


async def test_get_match_detail_includes_players_sets_and_statistics(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    player1, player2, match = await _seed_match(seeded_session, make_player)

    response = await api_client.get(f"/api/v1/matches/{match.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["player1"]["name"] == "Novak Djokovic"
    assert body["player2"]["name"] == "Carlos Alcaraz"
    assert body["tournament_edition"]["tournament_name"] == "Wimbledon"
    assert body["tournament_edition"]["surface"] == "grass"
    assert len(body["sets"]) == 1
    assert body["sets"][0]["player1_games"] == 6
    assert str(player1.id) in body["statistics"]
    assert body["statistics"][str(player1.id)]["aces"] == 12


async def test_get_match_not_found_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.get(f"/api/v1/matches/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_head_to_head_endpoint_returns_correct_counts(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    player1, player2, _match = await _seed_match(seeded_session, make_player)

    response = await api_client.get(
        "/api/v1/matches/head-to-head",
        params={"player1_id": str(player1.id), "player2_id": str(player2.id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["player1_wins"] == 1
    assert body["player2_wins"] == 0
    assert body["total_matches"] == 1


async def test_head_to_head_is_order_independent_via_api(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    player1, player2, _match = await _seed_match(seeded_session, make_player)

    forward = await api_client.get(
        "/api/v1/matches/head-to-head",
        params={"player1_id": str(player1.id), "player2_id": str(player2.id)},
    )
    backward = await api_client.get(
        "/api/v1/matches/head-to-head",
        params={"player1_id": str(player2.id), "player2_id": str(player1.id)},
    )

    assert forward.json()["total_matches"] == backward.json()["total_matches"]


async def test_head_to_head_missing_player_returns_404(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    player1 = make_player()
    seeded_session.add(player1)
    await seeded_session.flush()

    response = await api_client.get(
        "/api/v1/matches/head-to-head",
        params={"player1_id": str(player1.id), "player2_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404
