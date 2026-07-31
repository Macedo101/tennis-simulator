"""Teste end-to-end: a jornada completa de um utilizador, através da
API HTTP real (não chamadas diretas a serviços/repositórios).

Liga todos os módulos numa única jornada contínua: registo -> login ->
consulta de jogadores -> simulação Monte Carlo (assíncrona, Celery em
modo eager) -> polling do resultado -> previsão ML -> rotação de
refresh token -> logout. Usa um ficheiro SQLite partilhado (não
memória) pelo mesmo motivo do Módulo 8: a tarefa Celery abre a sua
própria ligação à BD, que só vê dados já commitados num ficheiro real.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - regista todos os modelos em Base.metadata
import app.tasks.simulation_tasks as simulation_tasks_module
from app.api.deps import get_match_outcome_model
from app.core.config import Settings
from app.db.base import Base, get_db_session
from app.main import app
from app.ml.dataset import generate_synthetic_dataset
from app.ml.model import MatchOutcomeModel
from app.models.lookup import Country, Surface
from app.models.match import Match
from app.models.player import Player
from app.models.tournament import Tournament, TournamentEdition
from app.tasks.celery_app import celery_app


@pytest_asyncio.fixture
async def e2e_client(tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    db_path = tmp_path / "e2e.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    # Dados de referência que só um admin poderia criar em produção
    # (não há ainda endpoint de escrita para jogadores/torneios — fica
    # para trabalho futuro); seed direto na BD é a forma correta de
    # preparar o cenário sem testar algo que não existe.
    import datetime

    async with session_factory() as session:
        session.add_all(
            [
                Country(iso_code="RS", name="Serbia"),
                Country(iso_code="ES", name="Spain"),
                Surface(id=1, name="hard"),
                Surface(id=2, name="clay"),
                Surface(id=3, name="grass"),
            ]
        )
        tournament = Tournament(name="Wimbledon", category="grand_slam")
        session.add(tournament)
        await session.flush()
        edition = TournamentEdition(
            tournament_id=tournament.id,
            year=2025,
            surface_id=3,
            start_date=datetime.date(2025, 6, 30),
            end_date=datetime.date(2025, 7, 13),
        )
        session.add(edition)
        player1 = Player(first_name="Novak", last_name="Djokovic", country_iso="RS")
        player2 = Player(first_name="Carlos", last_name="Alcaraz", country_iso="ES")
        session.add_all([player1, player2])
        await session.flush()
        match = Match(
            tournament_edition_id=edition.id,
            round="F",
            player1_id=player1.id,
            player2_id=player2.id,
            best_of=5,
            match_date=datetime.date(2025, 7, 13),
            status="scheduled",
        )
        session.add(match)
        await session.commit()
        seeded = {"player1_id": player1.id, "player2_id": player2.id, "match_id": match.id}

    async def _override_get_db_session() -> AsyncGenerator:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_get_db_session

    # A tarefa Celery cria o seu próprio engine a partir de
    # `get_settings().database_url` (ver `app/tasks/simulation_tasks.py`)
    # — aponta-se para o mesmo ficheiro SQLite partilhado, para que veja
    # os dados já commitados pelos pedidos HTTP (mesmo padrão do Módulo 8).
    test_settings = Settings(database_url=f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(simulation_tasks_module, "get_settings", lambda: test_settings)

    # Modo eager: `.delay()` corre a tarefa de forma síncrona, no mesmo
    # processo, sem exigir um broker/result-backend Redis real a
    # correr — sem isto, `.delay()` tenta mesmo ligar-se a
    # `redis://localhost:6379` e falha neste ambiente (ver Módulo 8/9).
    # Reposto no fim, para não vazar estado para outros testes da suite.
    original_eager = celery_app.conf.task_always_eager
    original_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    # Modelo ML "treinado" injetado (ver Módulo 6/9) — este teste valida
    # a jornada de ponta a ponta pela API, não o treino do modelo em si
    # (isso já está coberto pelos testes do Módulo 5).
    X_train, y_train = generate_synthetic_dataset(500, seed=1)
    trained_model = MatchOutcomeModel(model_type="baseline")
    trained_model.fit(X_train, y_train, log_to_mlflow=False)
    app.dependency_overrides[get_match_outcome_model] = lambda: trained_model

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.seeded = seeded  # type: ignore[attr-defined]
        yield client

    app.dependency_overrides.clear()
    celery_app.conf.task_always_eager = original_eager
    celery_app.conf.task_eager_propagates = original_propagates
    await engine.dispose()


async def test_full_user_journey(e2e_client: AsyncClient) -> None:
    client = e2e_client
    seeded = client.seeded  # type: ignore[attr-defined]

    # 1. Registo
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "joao@example.com",
            "password": "SenhaForte123",
            "full_name": "João Macedo",
        },
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == "joao@example.com"

    # 2. Login (OAuth2 password flow, form-urlencoded)
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": "joao@example.com", "password": "SenhaForte123"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 3. `/auth/me` confirma a identidade a partir do próprio token
    me_response = await client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "joao@example.com"

    # 4. Consulta de jogadores (paginada, pública)
    players_response = await client.get("/api/v1/players", params={"limit": 10})
    assert players_response.status_code == 200
    assert players_response.headers["X-RateLimit-Limit"] is not None
    player_names = {p["last_name"] for p in players_response.json()["data"]}
    assert {"Djokovic", "Alcaraz"} <= player_names

    # 5. Detalhe de um jogador
    player_detail_response = await client.get(f"/api/v1/players/{seeded['player1_id']}")
    assert player_detail_response.status_code == 200
    assert player_detail_response.json()["first_name"] == "Novak"

    # 6. Criar uma simulação (autenticado, assíncrona -> 202)
    create_sim_response = await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(seeded["player1_id"]),
            "player2_id": str(seeded["player2_id"]),
            "surface": "grass",
            "best_of": 5,
            "iterations": 5000,
        },
        headers=headers,
    )
    assert create_sim_response.status_code == 202
    simulation_id = create_sim_response.json()["id"]

    # 7. Polling do resultado — em modo eager (testes) já deve estar
    # `completed` no primeiro GET; em produção seria repetido até deixar
    # de estar `queued`/`running`.
    status_response = await client.get(
        f"/api/v1/simulations/{simulation_id}", headers=headers
    )
    assert status_response.status_code == 200
    result = status_response.json()
    assert result["status"] == "completed"
    assert 0.0 <= result["player1_win_probability"] <= 1.0
    assert result["confidence_interval"]["lower"] <= result["player1_win_probability"]

    # 8. Histórico de simulações do utilizador inclui a que acabámos de criar
    history_response = await client.get("/api/v1/simulations", headers=headers)
    assert history_response.status_code == 200
    assert any(s["id"] == simulation_id for s in history_response.json())

    # 9. Previsão ML para um jogo agendado
    prediction_response = await client.get(
        f"/api/v1/predictions/{seeded['match_id']}", headers=headers
    )
    assert prediction_response.status_code == 200
    assert 0.0 <= prediction_response.json()["player1_win_probability"] <= 1.0

    # 10. Rotação de refresh token
    refresh_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_response.status_code == 200
    new_tokens = refresh_response.json()
    assert new_tokens["access_token"] != access_token

    # O refresh token antigo, já rotacionado, não pode ser reutilizado.
    reuse_old_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert reuse_old_response.status_code == 401

    # 11. Logout com o refresh token novo
    logout_response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert logout_response.status_code == 204

    # Logout é idempotente — repetir não deve rebentar.
    second_logout_response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert second_logout_response.status_code == 204
