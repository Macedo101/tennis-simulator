"""Testes do `TournamentRepository`."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tournament import Tournament, TournamentEdition
from app.repositories.tournament_repository import TournamentRepository


@pytest.fixture
def repo(seeded_session: AsyncSession) -> TournamentRepository:
    return TournamentRepository(seeded_session)


async def _add_wimbledon(repo: TournamentRepository) -> Tournament:
    tournament = await repo.add(Tournament(name="Wimbledon", category="grand_slam"))
    return tournament


async def test_get_by_name_finds_exact_match(repo: TournamentRepository) -> None:
    await _add_wimbledon(repo)

    found = await repo.get_by_name("Wimbledon")

    assert found is not None
    assert found.category == "grand_slam"


async def test_get_by_name_returns_none_when_missing(repo: TournamentRepository) -> None:
    assert await repo.get_by_name("Roland Garros") is None


async def test_add_and_get_edition(repo: TournamentRepository) -> None:
    tournament = await _add_wimbledon(repo)
    edition = await repo.add_edition(
        TournamentEdition(
            tournament_id=tournament.id,
            year=2025,
            surface_id=3,  # grass
            start_date=datetime.date(2025, 6, 30),
            end_date=datetime.date(2025, 7, 13),
        )
    )

    fetched = await repo.get_edition(tournament.id, 2025)

    assert fetched is not None
    assert fetched.id == edition.id
    assert fetched.surface_id == 3


async def test_list_editions_by_surface(repo: TournamentRepository) -> None:
    tournament = await _add_wimbledon(repo)
    await repo.add_edition(
        TournamentEdition(
            tournament_id=tournament.id,
            year=2024,
            surface_id=3,
            start_date=datetime.date(2024, 7, 1),
            end_date=datetime.date(2024, 7, 14),
        )
    )
    await repo.add_edition(
        TournamentEdition(
            tournament_id=tournament.id,
            year=2025,
            surface_id=3,
            start_date=datetime.date(2025, 6, 30),
            end_date=datetime.date(2025, 7, 13),
        )
    )

    editions = await repo.list_editions_by_surface(3)

    assert len(editions) == 2
    # mais recente primeiro
    assert editions[0].year == 2025
