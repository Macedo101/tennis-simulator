"""Testes do `MatchRepository`, com foco na normalização de head-to-head."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, MatchSet, MatchStatistics
from app.models.tournament import Tournament, TournamentEdition
from app.repositories.match_repository import MatchRepository


@pytest.fixture
async def two_players_and_edition(seeded_session: AsyncSession, make_player):
    """Cria dois jogadores e uma edição de torneio para usar nos testes de Match."""
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
        surface_id=3,
        start_date=datetime.date(2025, 6, 30),
        end_date=datetime.date(2025, 7, 13),
    )
    seeded_session.add(edition)
    await seeded_session.flush()

    return player1, player2, edition


@pytest.fixture
def repo(seeded_session: AsyncSession) -> MatchRepository:
    return MatchRepository(seeded_session)


async def test_player_low_high_id_normalized_on_insert(
    repo: MatchRepository, two_players_and_edition
) -> None:
    player1, player2, edition = two_players_and_edition

    match = await repo.add(
        Match(
            tournament_edition_id=edition.id,
            round="F",
            player1_id=player1.id,
            player2_id=player2.id,
            best_of=5,
            match_date=datetime.date(2025, 7, 13),
        )
    )

    expected_low, expected_high = sorted((player1.id, player2.id), key=str)
    assert match.player_low_id == expected_low
    assert match.player_high_id == expected_high


async def test_head_to_head_is_order_independent(
    repo: MatchRepository, two_players_and_edition
) -> None:
    player1, player2, edition = two_players_and_edition
    await repo.add(
        Match(
            tournament_edition_id=edition.id,
            round="F",
            player1_id=player1.id,
            player2_id=player2.id,
            winner_id=player1.id,
            best_of=5,
            match_date=datetime.date(2025, 7, 13),
        )
    )

    # Passar os IDs pela ordem inversa deve devolver o mesmo resultado.
    h2h_order_a = await repo.get_head_to_head(player1.id, player2.id)
    h2h_order_b = await repo.get_head_to_head(player2.id, player1.id)

    assert len(h2h_order_a) == 1
    assert [m.id for m in h2h_order_a] == [m.id for m in h2h_order_b]


async def test_head_to_head_excludes_matches_against_other_players(
    repo: MatchRepository, two_players_and_edition, make_player, seeded_session
) -> None:
    player1, player2, edition = two_players_and_edition
    player3 = make_player(first_name="Daniil", last_name="Medvedev", country_iso="RS")
    seeded_session.add(player3)
    await seeded_session.flush()

    await repo.add(
        Match(
            tournament_edition_id=edition.id,
            round="F",
            player1_id=player1.id,
            player2_id=player2.id,
            best_of=5,
            match_date=datetime.date(2025, 7, 13),
        )
    )
    await repo.add(
        Match(
            tournament_edition_id=edition.id,
            round="SF",
            player1_id=player1.id,
            player2_id=player3.id,
            best_of=5,
            match_date=datetime.date(2025, 7, 11),
        )
    )

    h2h = await repo.get_head_to_head(player1.id, player2.id)

    assert len(h2h) == 1


async def test_get_with_details_eager_loads_sets_and_statistics(
    repo: MatchRepository, two_players_and_edition, seeded_session
) -> None:
    player1, player2, edition = two_players_and_edition
    match = await repo.add(
        Match(
            tournament_edition_id=edition.id,
            round="F",
            player1_id=player1.id,
            player2_id=player2.id,
            best_of=5,
            match_date=datetime.date(2025, 7, 13),
        )
    )
    seeded_session.add(
        MatchSet(match_id=match.id, set_number=1, player1_games=6, player2_games=4)
    )
    seeded_session.add(
        MatchStatistics(match_id=match.id, player_id=player1.id, aces=12, double_faults=2)
    )
    await seeded_session.flush()
    seeded_session.expunge_all()  # força recarregar do zero, sem cache de identidade

    fetched = await repo.get_with_details(match.id)

    assert fetched is not None
    assert len(fetched.sets) == 1
    assert fetched.sets[0].player1_games == 6
    assert len(fetched.statistics) == 1
    assert fetched.statistics[0].aces == 12


async def test_list_for_player_finds_matches_as_either_participant(
    repo: MatchRepository, two_players_and_edition
) -> None:
    player1, player2, edition = two_players_and_edition
    await repo.add(
        Match(
            tournament_edition_id=edition.id,
            round="F",
            player1_id=player1.id,
            player2_id=player2.id,
            best_of=5,
            match_date=datetime.date(2025, 7, 13),
        )
    )

    matches_p1 = await repo.list_for_player(player1.id)
    matches_p2 = await repo.list_for_player(player2.id)

    assert len(matches_p1) == 1
    assert len(matches_p2) == 1
