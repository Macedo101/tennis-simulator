"""Testes de integração do router de previsões (`/api/v1/predictions`)."""
from __future__ import annotations

import datetime
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_match_outcome_model
from app.main import app
from app.ml.dataset import generate_synthetic_dataset
from app.ml.model import MatchOutcomeModel
from app.models.match import Match
from app.models.player import PlayerRanking
from app.models.tournament import Tournament, TournamentEdition


async def test_prediction_returns_503_when_no_model_available(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    """Sem override da dependency, o modelo real é procurado em disco e não
    existe neste ambiente de teste — deve devolver 503, não simular uma previsão."""
    player1 = make_player(first_name="Novak", last_name="Djokovic")
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
    match = Match(
        tournament_edition_id=edition.id,
        round="F",
        player1_id=player1.id,
        player2_id=player2.id,
        best_of=5,
        match_date=datetime.date(2025, 7, 13),
        status="scheduled",
    )
    seeded_session.add(match)
    await seeded_session.flush()

    response = await api_client.get(f"/api/v1/predictions/{match.id}")

    assert response.status_code == 503
    assert response.json()["type"].endswith("model-unavailable")


async def test_prediction_returns_probability_with_trained_model(
    api_client: AsyncClient, seeded_session: AsyncSession, make_player
) -> None:
    """Com um modelo treinado injetado via dependency override, a previsão
    deve ser servida normalmente (200), com probabilidade em [0, 1]."""
    player1 = make_player(first_name="Novak", last_name="Djokovic")
    player2 = make_player(first_name="Carlos", last_name="Alcaraz", country_iso="ES")
    seeded_session.add_all([player1, player2])
    await seeded_session.flush()
    seeded_session.add_all(
        [
            PlayerRanking(
                player_id=player1.id,
                ranking_date=datetime.date(2026, 1, 1),
                rank_position=1,
                points=9000,
            ),
            PlayerRanking(
                player_id=player2.id,
                ranking_date=datetime.date(2026, 1, 1),
                rank_position=3,
                points=7000,
            ),
        ]
    )

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
    match = Match(
        tournament_edition_id=edition.id,
        round="F",
        player1_id=player1.id,
        player2_id=player2.id,
        best_of=5,
        match_date=datetime.date(2025, 7, 13),
        status="scheduled",
    )
    seeded_session.add(match)
    await seeded_session.flush()

    X_train, y_train = generate_synthetic_dataset(500, seed=1)
    trained_model = MatchOutcomeModel(model_type="baseline")
    trained_model.fit(X_train, y_train, log_to_mlflow=False)

    app.dependency_overrides[get_match_outcome_model] = lambda: trained_model
    try:
        response = await api_client.get(f"/api/v1/predictions/{match.id}")
    finally:
        del app.dependency_overrides[get_match_outcome_model]

    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["player1_win_probability"] <= 1.0
    assert body["model"]["name"] == "xgboost-calibrated-v1"


async def test_prediction_for_missing_match_returns_404(
    api_client: AsyncClient,
) -> None:
    trained_model = MatchOutcomeModel(model_type="baseline")
    X_train, y_train = generate_synthetic_dataset(200, seed=1)
    trained_model.fit(X_train, y_train, log_to_mlflow=False)

    app.dependency_overrides[get_match_outcome_model] = lambda: trained_model
    try:
        response = await api_client.get(f"/api/v1/predictions/{uuid.uuid4()}")
    finally:
        del app.dependency_overrides[get_match_outcome_model]

    assert response.status_code == 404
