"""Testes do `PlayerStatsService`."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, MatchStatistics
from app.models.tournament import Tournament, TournamentEdition
from app.repositories.exceptions import EntityNotFoundError
from app.repositories.match_repository import MatchRepository
from app.repositories.player_repository import PlayerRepository
from app.services.player_stats_service import PlayerStatsService


@pytest.fixture
def service(seeded_session: AsyncSession) -> PlayerStatsService:
    return PlayerStatsService(
        PlayerRepository(seeded_session), MatchRepository(seeded_session)
    )


@pytest.fixture
async def two_players_and_grass_edition(seeded_session: AsyncSession, make_player):
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

    return player1, player2, edition


async def _add_completed_match(
    session: AsyncSession,
    edition: TournamentEdition,
    player1_id,
    player2_id,
    winner_id,
    match_date: datetime.date,
    *,
    round_: str = "F",
) -> Match:
    match = Match(
        tournament_edition_id=edition.id,
        round=round_,
        player1_id=player1_id,
        player2_id=player2_id,
        winner_id=winner_id,
        best_of=5,
        match_date=match_date,
        status="completed",
    )
    session.add(match)
    await session.flush()
    return match


async def test_get_recent_form_raises_when_player_missing(service: PlayerStatsService) -> None:
    import uuid

    with pytest.raises(EntityNotFoundError):
        await service.get_recent_form(uuid.uuid4())


async def test_get_recent_form_counts_wins_and_losses(
    service: PlayerStatsService, two_players_and_grass_edition, seeded_session
) -> None:
    player1, player2, edition = two_players_and_grass_edition

    await _add_completed_match(
        seeded_session, edition, player1.id, player2.id, player1.id, datetime.date(2025, 7, 1)
    )
    await _add_completed_match(
        seeded_session, edition, player1.id, player2.id, player2.id, datetime.date(2025, 7, 5)
    )
    await _add_completed_match(
        seeded_session, edition, player1.id, player2.id, player1.id, datetime.date(2025, 7, 10)
    )

    form = await service.get_recent_form(player1.id, n_matches=10)

    assert form.matches_considered == 3
    assert form.wins == 2
    assert form.losses == 1
    assert form.win_rate == pytest.approx(0.6667, rel=1e-3)


async def test_get_recent_form_respects_n_matches_window(
    service: PlayerStatsService, two_players_and_grass_edition, seeded_session
) -> None:
    player1, player2, edition = two_players_and_grass_edition

    for i in range(5):
        await _add_completed_match(
            seeded_session,
            edition,
            player1.id,
            player2.id,
            player1.id,
            datetime.date(2025, 7, 1) + datetime.timedelta(days=i),
        )

    form = await service.get_recent_form(player1.id, n_matches=2)

    assert form.matches_considered == 2


async def test_get_recent_form_no_matches_returns_zero_win_rate(
    service: PlayerStatsService, two_players_and_grass_edition
) -> None:
    player1, _player2, _edition = two_players_and_grass_edition

    form = await service.get_recent_form(player1.id)

    assert form.matches_considered == 0
    assert form.win_rate == 0.0


async def test_get_surface_stats_aggregates_wins_and_serve_pct(
    service: PlayerStatsService, two_players_and_grass_edition, seeded_session
) -> None:
    player1, player2, edition = two_players_and_grass_edition

    match1 = await _add_completed_match(
        seeded_session, edition, player1.id, player2.id, player1.id, datetime.date(2025, 7, 1)
    )
    seeded_session.add(
        MatchStatistics(
            match_id=match1.id,
            player_id=player1.id,
            first_serve_pct=Decimal("65.00"),
            first_serve_points_won_pct=Decimal("70.00"),
        )
    )
    match2 = await _add_completed_match(
        seeded_session, edition, player1.id, player2.id, player2.id, datetime.date(2025, 7, 5)
    )
    seeded_session.add(
        MatchStatistics(
            match_id=match2.id,
            player_id=player1.id,
            first_serve_pct=Decimal("55.00"),
            first_serve_points_won_pct=Decimal("60.00"),
        )
    )
    await seeded_session.flush()

    stats = await service.get_surface_stats(player1.id, surface_id=3)

    assert stats.wins == 1
    assert stats.losses == 1
    assert stats.matches_played == 2
    assert stats.avg_first_serve_pct == pytest.approx(60.0)
    assert stats.avg_first_serve_points_won_pct == pytest.approx(65.0)


async def test_get_surface_stats_no_data_returns_none_averages(
    service: PlayerStatsService, two_players_and_grass_edition
) -> None:
    player1, _player2, _edition = two_players_and_grass_edition

    stats = await service.get_surface_stats(player1.id, surface_id=3)

    assert stats.matches_played == 0
    assert stats.avg_first_serve_pct is None
    assert stats.avg_first_serve_points_won_pct is None


async def test_get_surface_stats_ignores_other_surfaces(
    service: PlayerStatsService, two_players_and_grass_edition, seeded_session
) -> None:
    player1, player2, edition = two_players_and_grass_edition

    await _add_completed_match(
        seeded_session, edition, player1.id, player2.id, player1.id, datetime.date(2025, 7, 1)
    )

    clay_stats = await service.get_surface_stats(player1.id, surface_id=2)  # clay

    assert clay_stats.matches_played == 0


async def test_get_head_to_head_summary_counts_correctly(
    service: PlayerStatsService, two_players_and_grass_edition, seeded_session
) -> None:
    player1, player2, edition = two_players_and_grass_edition

    await _add_completed_match(
        seeded_session, edition, player1.id, player2.id, player1.id, datetime.date(2025, 7, 1)
    )
    await _add_completed_match(
        seeded_session, edition, player1.id, player2.id, player2.id, datetime.date(2025, 7, 8)
    )

    summary = await service.get_head_to_head_summary(player1.id, player2.id)

    assert summary.player1_wins == 1
    assert summary.player2_wins == 1
    assert summary.total_matches == 2
    assert summary.last_meeting_date == datetime.date(2025, 7, 8)


async def test_get_head_to_head_summary_raises_when_player_missing(
    service: PlayerStatsService, two_players_and_grass_edition
) -> None:
    import uuid

    player1, _player2, _edition = two_players_and_grass_edition

    with pytest.raises(EntityNotFoundError):
        await service.get_head_to_head_summary(player1.id, uuid.uuid4())
