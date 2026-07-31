"""Testes de engenharia de features (`app.ml.features`)."""
from __future__ import annotations

from app.ml.features import FEATURE_NAMES, build_feature_vector
from app.services.dto import (
    HeadToHeadSummaryResult,
    RecentFormResult,
    SurfaceStatsResult,
)


def _form(player_id, wins, losses):
    return RecentFormResult(
        player_id=player_id, matches_considered=wins + losses, wins=wins, losses=losses
    )


def _surface_stats(player_id, surface_id, wins, losses, avg_fs_pct):
    return SurfaceStatsResult(
        player_id=player_id,
        surface_id=surface_id,
        wins=wins,
        losses=losses,
        avg_first_serve_pct=avg_fs_pct,
        avg_first_serve_points_won_pct=None,
        avg_second_serve_points_won_pct=None,
    )


def test_feature_vector_has_expected_length_and_order() -> None:
    import uuid

    p1, p2 = uuid.uuid4(), uuid.uuid4()
    vector = build_feature_vector(
        player1_rank=1,
        player2_rank=5,
        player1_points=9000,
        player2_points=6000,
        player1_form=_form(p1, 7, 3),
        player2_form=_form(p2, 5, 5),
        player1_surface_stats=_surface_stats(p1, 3, 8, 2, 65.0),
        player2_surface_stats=_surface_stats(p2, 3, 4, 6, 60.0),
        h2h=HeadToHeadSummaryResult(
            player1_id=p1, player2_id=p2, player1_wins=3, player2_wins=1,
            last_meeting_date=None,
        ),
    )

    array = vector.to_array()
    assert len(array) == len(FEATURE_NAMES)


def test_rank_diff_favors_higher_ranked_player1() -> None:
    """Jogador 1 com ranking melhor (nº mais baixo) deve dar rank_diff positivo."""
    import uuid

    p1, p2 = uuid.uuid4(), uuid.uuid4()
    vector = build_feature_vector(
        player1_rank=1,  # melhor ranking
        player2_rank=50,
        player1_points=10000,
        player2_points=2000,
        player1_form=_form(p1, 5, 5),
        player2_form=_form(p2, 5, 5),
        player1_surface_stats=_surface_stats(p1, 1, 5, 5, 60.0),
        player2_surface_stats=_surface_stats(p2, 1, 5, 5, 60.0),
        h2h=HeadToHeadSummaryResult(
            player1_id=p1, player2_id=p2, player1_wins=0, player2_wins=0,
            last_meeting_date=None,
        ),
    )

    assert vector.rank_diff > 0
    assert vector.points_diff > 0


def test_h2h_win_rate_diff_zero_when_no_prior_meetings() -> None:
    import uuid

    p1, p2 = uuid.uuid4(), uuid.uuid4()
    vector = build_feature_vector(
        player1_rank=10,
        player2_rank=10,
        player1_points=5000,
        player2_points=5000,
        player1_form=_form(p1, 0, 0),
        player2_form=_form(p2, 0, 0),
        player1_surface_stats=_surface_stats(p1, 1, 0, 0, None),
        player2_surface_stats=_surface_stats(p2, 1, 0, 0, None),
        h2h=HeadToHeadSummaryResult(
            player1_id=p1, player2_id=p2, player1_wins=0, player2_wins=0,
            last_meeting_date=None,
        ),
    )

    assert vector.h2h_win_rate_diff == 0.0
    assert vector.surface_first_serve_pct_diff == 0.0


def test_feature_vector_is_antisymmetric_when_players_swapped() -> None:
    """Trocar jogador1<->jogador2 deve inverter exatamente o sinal das features."""
    import uuid

    a, b = uuid.uuid4(), uuid.uuid4()
    common_kwargs = dict(
        player1_form=_form(a, 7, 3),
        player2_form=_form(b, 4, 6),
        player1_surface_stats=_surface_stats(a, 2, 8, 2, 68.0),
        player2_surface_stats=_surface_stats(b, 2, 3, 7, 55.0),
    )

    forward = build_feature_vector(
        player1_rank=2,
        player2_rank=20,
        player1_points=8000,
        player2_points=3000,
        h2h=HeadToHeadSummaryResult(
            player1_id=a, player2_id=b, player1_wins=4, player2_wins=1,
            last_meeting_date=None,
        ),
        **common_kwargs,
    )
    backward = build_feature_vector(
        player1_rank=20,
        player2_rank=2,
        player1_points=3000,
        player2_points=8000,
        h2h=HeadToHeadSummaryResult(
            player1_id=b, player2_id=a, player1_wins=1, player2_wins=4,
            last_meeting_date=None,
        ),
        player1_form=common_kwargs["player2_form"],
        player2_form=common_kwargs["player1_form"],
        player1_surface_stats=common_kwargs["player2_surface_stats"],
        player2_surface_stats=common_kwargs["player1_surface_stats"],
    )

    for f_val, b_val in zip(forward.to_array(), backward.to_array(), strict=True):
        assert f_val == -b_val
