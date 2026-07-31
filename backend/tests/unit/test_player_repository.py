"""Testes do `PlayerRepository`."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import PlayerRanking
from app.repositories.player_repository import PlayerRepository


@pytest.fixture
def repo(seeded_session: AsyncSession) -> PlayerRepository:
    return PlayerRepository(seeded_session)


async def test_search_by_name_finds_partial_match(repo: PlayerRepository, make_player) -> None:
    await repo.add(make_player(first_name="Novak", last_name="Djokovic"))
    await repo.add(make_player(first_name="Carlos", last_name="Alcaraz", country_iso="ES"))

    results = await repo.search_by_name("djoko")

    assert len(results) == 1
    assert results[0].last_name == "Djokovic"


async def test_search_by_name_no_match_returns_empty(repo: PlayerRepository, make_player) -> None:
    await repo.add(make_player())

    results = await repo.search_by_name("nadal")

    assert results == []


async def test_get_by_identity_finds_exact_match(repo: PlayerRepository, make_player) -> None:
    await repo.add(make_player())

    found = await repo.get_by_identity("Novak", "Djokovic", datetime.date(1987, 5, 22))

    assert found is not None
    assert found.first_name == "Novak"


async def test_get_by_identity_returns_none_for_different_dob(
    repo: PlayerRepository, make_player
) -> None:
    await repo.add(make_player())

    found = await repo.get_by_identity("Novak", "Djokovic", datetime.date(1990, 1, 1))

    assert found is None


async def test_list_by_country_filters_correctly(repo: PlayerRepository, make_player) -> None:
    await repo.add(make_player(first_name="Novak", last_name="Djokovic", country_iso="RS"))
    await repo.add(make_player(first_name="Carlos", last_name="Alcaraz", country_iso="ES"))

    results = await repo.list_by_country("RS")

    assert len(results) == 1
    assert results[0].country_iso == "RS"


async def test_get_current_ranking_returns_most_recent(repo: PlayerRepository, make_player) -> None:
    player = await repo.add(make_player())
    repo._session.add_all(
        [
            PlayerRanking(
                player_id=player.id,
                ranking_date=datetime.date(2026, 1, 5),
                rank_position=3,
                points=8000,
            ),
            PlayerRanking(
                player_id=player.id,
                ranking_date=datetime.date(2026, 7, 20),
                rank_position=1,
                points=9500,
            ),
        ]
    )
    await repo._session.flush()

    current = await repo.get_current_ranking(player.id)

    assert current is not None
    assert current.ranking_date == datetime.date(2026, 7, 20)
    assert current.rank_position == 1


async def test_get_current_ranking_none_when_no_history(
    repo: PlayerRepository, make_player
) -> None:
    player = await repo.add(make_player())

    assert await repo.get_current_ranking(player.id) is None


async def test_get_ranking_history_orders_most_recent_first_and_filters_since(
    repo: PlayerRepository, make_player
) -> None:
    player = await repo.add(make_player())
    repo._session.add_all(
        [
            PlayerRanking(
                player_id=player.id,
                ranking_date=datetime.date(2025, 1, 1),
                rank_position=5,
                points=6000,
            ),
            PlayerRanking(
                player_id=player.id,
                ranking_date=datetime.date(2026, 1, 1),
                rank_position=2,
                points=9000,
            ),
        ]
    )
    await repo._session.flush()

    history = await repo.get_ranking_history(player.id, since=datetime.date(2025, 6, 1))

    assert len(history) == 1
    assert history[0].ranking_date == datetime.date(2026, 1, 1)
