"""Router de previsões (`/api/v1/predictions`), servidas pelo modelo ML."""
from __future__ import annotations

import datetime
import time
from typing import Annotated
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Path

from app.api.deps import (
    MatchOutcomeModelDep,
    MatchRepo,
    PlayerRepo,
    PlayerStatsServiceDep,
    TournamentRepo,
)
from app.api.schemas.prediction import ModelRef, PredictionResponse
from app.core.metrics import PREDICTION_DURATION_SECONDS
from app.ml.features import build_feature_vector
from app.repositories.exceptions import EntityNotFoundError

router = APIRouter(prefix="/predictions", tags=["predictions"])

# Fallback usado quando um jogador não tem nenhum registo de ranking na
# BD (ex.: dados de teste incompletos) — um ranking muito baixo e zero
# pontos é a suposição mais neutra possível (não favorece nenhum lado
# artificialmente), documentado explicitamente em vez de silenciado.
_UNRANKED_FALLBACK_RANK = 2000
_UNRANKED_FALLBACK_POINTS = 0

_MODEL_NAME = "xgboost-calibrated-v1"
_MODEL_VERSION = "1.0.0"


@router.get("/{match_id}", response_model=PredictionResponse)
async def get_match_prediction(
    match_id: Annotated[UUID, Path()],
    match_repository: MatchRepo,
    tournament_repository: TournamentRepo,
    player_repository: PlayerRepo,
    stats_service: PlayerStatsServiceDep,
    model: MatchOutcomeModelDep,
) -> PredictionResponse:
    match = await match_repository.get_by_id(match_id)
    if match is None:
        raise EntityNotFoundError("Match", match_id)

    edition = await tournament_repository.get_edition_by_id(match.tournament_edition_id)
    if edition is None:
        raise EntityNotFoundError("TournamentEdition", match.tournament_edition_id)

    player1_ranking = await player_repository.get_current_ranking(match.player1_id)
    player2_ranking = await player_repository.get_current_ranking(match.player2_id)

    p1_rank = player1_ranking.rank_position if player1_ranking else _UNRANKED_FALLBACK_RANK
    p1_points = player1_ranking.points if player1_ranking else _UNRANKED_FALLBACK_POINTS
    p2_rank = player2_ranking.rank_position if player2_ranking else _UNRANKED_FALLBACK_RANK
    p2_points = player2_ranking.points if player2_ranking else _UNRANKED_FALLBACK_POINTS

    player1_form = await stats_service.get_recent_form(match.player1_id)
    player2_form = await stats_service.get_recent_form(match.player2_id)
    player1_surface_stats = await stats_service.get_surface_stats(
        match.player1_id, edition.surface_id
    )
    player2_surface_stats = await stats_service.get_surface_stats(
        match.player2_id, edition.surface_id
    )
    h2h = await stats_service.get_head_to_head_summary(match.player1_id, match.player2_id)

    started_at = time.perf_counter()
    feature_vector = build_feature_vector(
        player1_rank=p1_rank,
        player2_rank=p2_rank,
        player1_points=p1_points,
        player2_points=p2_points,
        player1_form=player1_form,
        player2_form=player2_form,
        player1_surface_stats=player1_surface_stats,
        player2_surface_stats=player2_surface_stats,
        h2h=h2h,
    )

    X = np.array([feature_vector.to_array()])
    probability = float(model.predict_proba(X)[0])
    PREDICTION_DURATION_SECONDS.observe(time.perf_counter() - started_at)

    return PredictionResponse(
        match_id=match_id,
        model=ModelRef(name=_MODEL_NAME, version=_MODEL_VERSION),
        player1_win_probability=round(probability, 4),
        predicted_at=datetime.datetime.now(datetime.UTC),
    )
