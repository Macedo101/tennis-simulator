"""Testes de integração do router de simulações (`/api/v1/simulations`).

Estes testes usam um ficheiro SQLite temporário partilhado (não SQLite
em memória) — a tarefa Celery corre com o seu próprio engine/ligação
(ver `app/tasks/simulation_tasks.py`), e uma BD em memória não seria
visível entre ligações diferentes. Um ficheiro partilhado permite
validar o fluxo assíncrono completo (pedido HTTP -> commit -> tarefa
Celery em modo eager -> commit do resultado -> novo pedido HTTP vê o
resultado), exatamente como aconteceria em produção entre processos.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401 - regista todos os modelos
import app.tasks.simulation_tasks as simulation_tasks_module
from app.core.config import Settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base, get_db_session
from app.main import app
from app.models.auth import User
from app.models.lookup import Country, Surface
from app.models.player import Player
from app.tasks.celery_app import celery_app


@pytest_asyncio.fixture
async def simulation_setup(monkeypatch, tmp_path) -> AsyncGenerator[dict, None]:
    db_path = tmp_path / "simulations_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

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
        user_a = User(
            email="alice@test.com",
            full_name="Alice",
            hashed_password=hash_password("StrongPass123"),
            role="user",
        )
        user_b = User(
            email="bob@test.com",
            full_name="Bob",
            hashed_password=hash_password("StrongPass123"),
            role="user",
        )
        player1 = Player(first_name="Novak", last_name="Djokovic", country_iso="RS")
        player2 = Player(first_name="Carlos", last_name="Alcaraz", country_iso="ES")
        session.add_all([user_a, user_b, player1, player2])
        await session.commit()
        ids = {
            "user_a_id": user_a.id,
            "user_b_id": user_b.id,
            "player1_id": player1.id,
            "player2_id": player2.id,
        }

    async def _override_get_db_session() -> AsyncGenerator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    # A tarefa Celery cria o seu próprio engine a partir de `get_settings()`
    # (ver `_make_session_factory`) — substituímos por settings apontando
    # para o mesmo ficheiro, para que veja os mesmos dados commitados.
    test_settings = Settings(database_url=db_url)
    monkeypatch.setattr(simulation_tasks_module, "get_settings", lambda: test_settings)

    celery_app.conf.task_always_eager = True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ids["client"] = client
        ids["token_a"] = create_access_token(user_id=user_a.id, role="user")
        ids["token_b"] = create_access_token(user_id=user_b.id, role="user")
        yield ids

    app.dependency_overrides.clear()
    celery_app.conf.task_always_eager = False
    await engine.dispose()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_simulation_runs_eagerly_and_completes(simulation_setup: dict) -> None:
    client: AsyncClient = simulation_setup["client"]

    response = await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(simulation_setup["player1_id"]),
            "player2_id": str(simulation_setup["player2_id"]),
            "surface": "clay",
            "best_of": 3,
            "iterations": 1000,
        },
        headers=_auth_headers(simulation_setup["token_a"]),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    simulation_id = body["id"]
    assert body["poll_url"] == f"/api/v1/simulations/{simulation_id}"

    status_response = await client.get(
        f"/api/v1/simulations/{simulation_id}", headers=_auth_headers(simulation_setup["token_a"])
    )
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] == "completed"
    assert 0.0 <= status_body["player1_win_probability"] <= 1.0
    ci = status_body["confidence_interval"]
    assert ci["lower"] <= status_body["player1_win_probability"] <= ci["upper"]
    assert status_body["avg_match_duration_minutes"] > 0
    assert sum(status_body["sets_won_distribution"].values()) == 1.0


async def test_create_simulation_works_anonymously(simulation_setup: dict) -> None:
    """O simulador é aberto a qualquer pessoa — não exige conta."""
    client: AsyncClient = simulation_setup["client"]

    create_response = await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(simulation_setup["player1_id"]),
            "player2_id": str(simulation_setup["player2_id"]),
            "surface": "clay",
            "best_of": 3,
            "iterations": 1000,
        },
    )
    assert create_response.status_code == 202
    simulation_id = create_response.json()["id"]

    # Visível por quem tiver o ID, mesmo sem login (é uma simulação sem dono).
    status_response = await client.get(f"/api/v1/simulations/{simulation_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"

    # Mas não aparece no histórico de ninguém — não tem dono a quem associar.
    history_response = await client.get(
        "/api/v1/simulations", headers=_auth_headers(simulation_setup["token_a"])
    )
    assert simulation_id not in {s["id"] for s in history_response.json()}


async def test_get_anonymous_simulation_not_owned_by_logged_in_user(
    simulation_setup: dict,
) -> None:
    """Uma simulação de outro utilizador continua protegida — só as
    anónimas (sem dono) ficam abertas a qualquer pedido com o ID."""
    client: AsyncClient = simulation_setup["client"]

    create_response = await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(simulation_setup["player1_id"]),
            "player2_id": str(simulation_setup["player2_id"]),
            "surface": "grass",
            "best_of": 3,
            "iterations": 1000,
        },
        headers=_auth_headers(simulation_setup["token_a"]),
    )
    simulation_id = create_response.json()["id"]

    # Outro utilizador, sem ser dono, continua a levar 404.
    other_user_response = await client.get(
        f"/api/v1/simulations/{simulation_id}", headers=_auth_headers(simulation_setup["token_b"])
    )
    assert other_user_response.status_code == 404

    # Um visitante sem sessão nenhuma também não vê a simulação de outra conta.
    anonymous_response = await client.get(f"/api/v1/simulations/{simulation_id}")
    assert anonymous_response.status_code == 404


async def test_create_simulation_same_player_twice_returns_422(simulation_setup: dict) -> None:
    client: AsyncClient = simulation_setup["client"]

    response = await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(simulation_setup["player1_id"]),
            "player2_id": str(simulation_setup["player1_id"]),
            "surface": "clay",
            "best_of": 3,
            "iterations": 1000,
        },
        headers=_auth_headers(simulation_setup["token_a"]),
    )

    assert response.status_code == 422


async def test_create_simulation_unknown_surface_returns_404(simulation_setup: dict) -> None:
    client: AsyncClient = simulation_setup["client"]

    response = await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(simulation_setup["player1_id"]),
            "player2_id": str(simulation_setup["player2_id"]),
            "surface": "ice",
            "best_of": 3,
            "iterations": 1000,
        },
        headers=_auth_headers(simulation_setup["token_a"]),
    )

    assert response.status_code == 404


async def test_create_simulation_unknown_player_returns_404(simulation_setup: dict) -> None:
    client: AsyncClient = simulation_setup["client"]

    response = await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(uuid.uuid4()),
            "player2_id": str(simulation_setup["player2_id"]),
            "surface": "clay",
            "best_of": 3,
            "iterations": 1000,
        },
        headers=_auth_headers(simulation_setup["token_a"]),
    )

    assert response.status_code == 404


async def test_get_simulation_of_another_user_returns_404(simulation_setup: dict) -> None:
    client: AsyncClient = simulation_setup["client"]

    create_response = await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(simulation_setup["player1_id"]),
            "player2_id": str(simulation_setup["player2_id"]),
            "surface": "grass",
            "best_of": 3,
            "iterations": 1000,
        },
        headers=_auth_headers(simulation_setup["token_a"]),
    )
    simulation_id = create_response.json()["id"]

    response = await client.get(
        f"/api/v1/simulations/{simulation_id}", headers=_auth_headers(simulation_setup["token_b"])
    )

    assert response.status_code == 404


async def test_list_simulations_only_returns_own(simulation_setup: dict) -> None:
    client: AsyncClient = simulation_setup["client"]

    await client.post(
        "/api/v1/simulations",
        json={
            "player1_id": str(simulation_setup["player1_id"]),
            "player2_id": str(simulation_setup["player2_id"]),
            "surface": "hard",
            "best_of": 3,
            "iterations": 1000,
        },
        headers=_auth_headers(simulation_setup["token_a"]),
    )

    response_a = await client.get(
        "/api/v1/simulations", headers=_auth_headers(simulation_setup["token_a"])
    )
    response_b = await client.get(
        "/api/v1/simulations", headers=_auth_headers(simulation_setup["token_b"])
    )

    assert len(response_a.json()) == 1
    assert len(response_b.json()) == 0


async def test_get_unknown_simulation_returns_404(simulation_setup: dict) -> None:
    client: AsyncClient = simulation_setup["client"]

    response = await client.get(
        f"/api/v1/simulations/{uuid.uuid4()}", headers=_auth_headers(simulation_setup["token_a"])
    )

    assert response.status_code == 404


def test_websocket_streams_status_until_completed(simulation_setup: dict) -> None:
    """Usa o TestClient síncrono (não `httpx.AsyncClient`) só para este
    teste — é o cliente WebSocket suportado pelo Starlette; o resto da
    suite usa `httpx.AsyncClient` porque não precisa de WebSockets."""
    from starlette.testclient import TestClient

    with TestClient(app) as sync_client:
        create_response = sync_client.post(
            "/api/v1/simulations",
            json={
                "player1_id": str(simulation_setup["player1_id"]),
                "player2_id": str(simulation_setup["player2_id"]),
                "surface": "hard",
                "best_of": 3,
                "iterations": 1000,
            },
            headers=_auth_headers(simulation_setup["token_a"]),
        )
        simulation_id = create_response.json()["id"]

        # Modo eager: a simulação já está `completed` antes mesmo de o
        # websocket ligar (o `.delay()` correu de forma síncrona dentro
        # do próprio pedido POST) — a primeira mensagem já deve refletir
        # o estado final, sem exigir múltiplas iterações de polling.
        with sync_client.websocket_connect(
            f"/api/v1/simulations/{simulation_id}/ws?token={simulation_setup['token_a']}"
        ) as websocket:
            message = websocket.receive_json()
            assert message["status"] == "completed"
            assert 0.0 <= message["player1_win_probability"] <= 1.0


def test_websocket_rejects_missing_token(simulation_setup: dict) -> None:
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as sync_client:
        create_response = sync_client.post(
            "/api/v1/simulations",
            json={
                "player1_id": str(simulation_setup["player1_id"]),
                "player2_id": str(simulation_setup["player2_id"]),
                "surface": "hard",
                "best_of": 3,
                "iterations": 1000,
            },
            headers=_auth_headers(simulation_setup["token_a"]),
        )
        simulation_id = create_response.json()["id"]

        with pytest.raises(WebSocketDisconnect), sync_client.websocket_connect(
            f"/api/v1/simulations/{simulation_id}/ws"
        ) as websocket:
            websocket.receive_json()


def test_websocket_rejects_other_users_simulation(simulation_setup: dict) -> None:
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as sync_client:
        create_response = sync_client.post(
            "/api/v1/simulations",
            json={
                "player1_id": str(simulation_setup["player1_id"]),
                "player2_id": str(simulation_setup["player2_id"]),
                "surface": "hard",
                "best_of": 3,
                "iterations": 1000,
            },
            headers=_auth_headers(simulation_setup["token_a"]),
        )
        simulation_id = create_response.json()["id"]

        with pytest.raises(WebSocketDisconnect), sync_client.websocket_connect(
            f"/api/v1/simulations/{simulation_id}/ws?token={simulation_setup['token_b']}"
        ) as websocket:
            websocket.receive_json()


async def test_simulation_specific_rate_limit_blocks_after_threshold(
    simulation_setup: dict, monkeypatch
) -> None:
    """Limite dedicado de 10/hora de simulações (independente do limite
    geral do middleware, Módulo 9) — usa `fakeredis` para tornar o
    bloqueio determinístico neste teste."""
    from fakeredis import aioredis as fake_aioredis

    import app.api.deps as deps_module

    fake_redis = fake_aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(deps_module, "get_redis_client", lambda: fake_redis)

    client: AsyncClient = simulation_setup["client"]
    payload = {
        "player1_id": str(simulation_setup["player1_id"]),
        "player2_id": str(simulation_setup["player2_id"]),
        "surface": "clay",
        "best_of": 3,
        "iterations": 1000,
    }
    headers = _auth_headers(simulation_setup["token_a"])

    for i in range(10):
        response = await client.post("/api/v1/simulations", json=payload, headers=headers)
        assert response.status_code == 202, f"pedido {i + 1} deveria ser aceite"

    blocked_response = await client.post("/api/v1/simulations", json=payload, headers=headers)

    assert blocked_response.status_code == 429
    assert blocked_response.json()["type"].endswith("rate-limit-exceeded")

    await fake_redis.flushall()
    await fake_redis.aclose()
