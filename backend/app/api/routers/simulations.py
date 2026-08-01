"""Router de simulações Monte Carlo (`/api/v1/simulations`).

Rate limiting dedicado (10/hora por utilizador) e cache de resultados
de simulações idênticas — ambos via `app.cache` (Módulo 9).
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, WebSocket, WebSocketDisconnect, status

from app.api.deps import (
    AuthServiceDep,
    CurrentUser,
    DbSession,
    LookupRepo,
    OptionalCurrentUser,
    PlayerRepo,
    SimulationCacheDep,
    SimulationRepo,
    enforce_simulation_rate_limit,
)
from app.api.schemas.simulation import (
    ConfidenceInterval,
    SimulationAcceptedResponse,
    SimulationCreateRequest,
    SimulationStatusResponse,
)
from app.cache.simulation_cache import SimulationResultCache
from app.core.metrics import SIMULATION_CACHE_REQUESTS_TOTAL
from app.models.simulation import Simulation
from app.repositories.exceptions import EntityNotFoundError
from app.services.auth_service import InvalidCredentialsError
from app.tasks.simulation_tasks import run_simulation_task

router = APIRouter(prefix="/simulations", tags=["simulations"])

#: Intervalo entre atualizações de estado enviadas pelo WebSocket. Um
#: valor curto o suficiente para parecer "em tempo real" ao cliente,
#: sem sobrecarregar a BD com polling — a simulação em si corre em
#: segundos (motor vetorizado, Módulo 4), pelo que poucas iterações de
#: polling bastam mesmo no pior caso.
_WS_POLL_INTERVAL_SECONDS = 0.5


def _to_status_response(simulation: Simulation) -> SimulationStatusResponse:
    confidence_interval = None
    if (
        simulation.confidence_interval_lower is not None
        and simulation.confidence_interval_upper is not None
    ):
        confidence_interval = ConfidenceInterval(
            lower=simulation.confidence_interval_lower,
            upper=simulation.confidence_interval_upper,
        )

    return SimulationStatusResponse(
        id=simulation.id,
        status=simulation.status,
        player1_win_probability=simulation.player1_win_probability,
        confidence_interval=confidence_interval,
        sets_won_distribution=simulation.sets_won_distribution,
        avg_match_duration_minutes=simulation.avg_match_duration_minutes,
        error_message=simulation.error_message,
        completed_at=simulation.completed_at,
    )


@router.post(
    "",
    response_model=SimulationAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_simulation_rate_limit)],
)
async def create_simulation(
    payload: SimulationCreateRequest,
    current_user: OptionalCurrentUser,
    simulation_repository: SimulationRepo,
    player_repository: PlayerRepo,
    lookup_repository: LookupRepo,
    simulation_cache: SimulationCacheDep,
    session: DbSession,
) -> SimulationAcceptedResponse:
    if payload.player1_id == payload.player2_id:
        raise ValueError("player1_id e player2_id têm de ser jogadores diferentes.")

    await player_repository.get_by_id_or_raise(payload.player1_id)
    await player_repository.get_by_id_or_raise(payload.player2_id)

    surfaces = await lookup_repository.list_surfaces()
    surface = next((s for s in surfaces if s.name == payload.surface), None)
    if surface is None:
        raise EntityNotFoundError("Surface", payload.surface)

    cache_key = SimulationResultCache.build_key(
        player1_id=payload.player1_id,
        player2_id=payload.player2_id,
        surface_id=surface.id,
        best_of=payload.best_of,
        iterations=payload.iterations,
    )
    cached_result = await simulation_cache.get(cache_key)
    SIMULATION_CACHE_REQUESTS_TOTAL.labels(
        result="hit" if cached_result is not None else "miss"
    ).inc()

    simulation = Simulation(
        user_id=current_user.id if current_user else None,
        player1_id=payload.player1_id,
        player2_id=payload.player2_id,
        surface_id=surface.id,
        best_of=payload.best_of,
        iterations=payload.iterations,
        status="queued",
    )
    await simulation_repository.add(simulation)

    if cached_result is not None:
        # Cache hit: reaproveita o resultado de um pedido idêntico
        # recente — a simulação fica `completed` de imediato, sem
        # despachar Celery nem recomputar as iterações Monte Carlo.
        await simulation_repository.mark_completed(
            simulation,
            player1_win_probability=cached_result.player1_win_probability,
            confidence_interval_lower=cached_result.confidence_interval_lower,
            confidence_interval_upper=cached_result.confidence_interval_upper,
            sets_won_distribution=cached_result.sets_won_distribution,
            avg_match_duration_minutes=cached_result.avg_match_duration_minutes,
        )

    # Commit explícito aqui, antes do despacho — deliberadamente
    # diferente do padrão "commit só no fim do pedido" (Módulo 6/8): o
    # worker Celery abre a sua própria ligação/transação à BD (ver
    # `app/tasks/simulation_tasks.py`) e não veria esta linha se ainda
    # estivesse por confirmar na transação do pedido HTTP. Isto aplica-se
    # mesmo em modo eager de teste, onde a tarefa corre de forma síncrona
    # mas ainda assim com o seu próprio engine/sessão.
    await session.commit()

    if cached_result is None:
        # Despacho assíncrono: em produção publica na fila Celery/Redis
        # real; em testes, `celery_task_always_eager=True` corre a
        # tarefa de forma síncrona no mesmo processo (ver
        # `app/tasks/celery_app.py`). A própria tarefa grava o
        # resultado em cache ao terminar (ver `simulation_tasks.py`).
        run_simulation_task.delay(str(simulation.id))

    return SimulationAcceptedResponse(
        id=simulation.id,
        status=simulation.status,
        requested_at=simulation.requested_at,
        poll_url=f"/api/v1/simulations/{simulation.id}",
        websocket_url=f"/api/v1/simulations/{simulation.id}/ws",
    )


@router.get("/{simulation_id}", response_model=SimulationStatusResponse)
async def get_simulation(
    simulation_id: Annotated[UUID, Path()],
    current_user: OptionalCurrentUser,
    simulation_repository: SimulationRepo,
) -> SimulationStatusResponse:
    simulation = await simulation_repository.get_by_id_or_raise(simulation_id)
    if simulation.user_id is not None and (
        current_user is None or (
            simulation.user_id != current_user.id and current_user.role != "admin"
        )
    ):
        # Tratado como 404, não 403 — não revela a outros utilizadores
        # que uma simulação com este ID existe (evita enumeração).
        # Simulações anónimas (user_id None) são visíveis por quem
        # tiver o ID — o próprio UUID imprevisível já é a proteção,
        # tal como num link de partilha.
        raise EntityNotFoundError("Simulation", simulation_id)
    return _to_status_response(simulation)


@router.get("", response_model=list[SimulationStatusResponse])
async def list_simulations(
    current_user: CurrentUser,
    simulation_repository: SimulationRepo,
) -> list[SimulationStatusResponse]:
    """Histórico de simulações — exige conta (não há "histórico" sem
    identidade). O simulador em si (`POST`/`GET /{id}`) não exige."""
    simulations = await simulation_repository.list_for_user(current_user.id)
    return [_to_status_response(s) for s in simulations]


@router.websocket("/{simulation_id}/ws")
async def simulation_progress_ws(
    websocket: WebSocket,
    simulation_id: UUID,
    simulation_repository: SimulationRepo,
    auth_service: AuthServiceDep,
    session: DbSession,
    token: str | None = None,
) -> None:
    """Envia o estado da simulação por WebSocket até terminar (completed/failed).

    Autenticação por query param `?token=<access_token>`, não pelo
    header `Authorization` — o handshake de WebSocket feito pelo browser
    não permite cabeçalhos customizados. O `token` é opcional: uma
    simulação anónima (sem conta) pode ser seguida por quem tiver o
    link; uma simulação associada a uma conta exige o token de quem a
    criou (ou de um admin), tal como no `GET /simulations/{id}`.
    """
    await websocket.accept()
    try:
        current_user = None
        if token is not None:
            try:
                current_user = await auth_service.get_current_user(token)
            except InvalidCredentialsError:
                await websocket.close(code=4401, reason="Token inválido ou expirado.")
                return

        simulation = await simulation_repository.get_by_id(simulation_id)
        if simulation is None:
            await websocket.close(code=4404, reason="Simulação não encontrada.")
            return
        if simulation.user_id is not None and (
            current_user is None or (
                simulation.user_id != current_user.id and current_user.role != "admin"
            )
        ):
            await websocket.close(code=4404, reason="Simulação não encontrada.")
            return

        while True:
            await session.refresh(simulation)
            await websocket.send_json(_to_status_response(simulation).model_dump(mode="json"))
            if simulation.status in ("completed", "failed"):
                break
            await asyncio.sleep(_WS_POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        # Cliente desligou-se antes do fim — não é um erro do servidor.
        return
    finally:
        with contextlib.suppress(RuntimeError):
            # Já estava fechado (ex.: um dos `close()` explícitos acima).
            await websocket.close()
