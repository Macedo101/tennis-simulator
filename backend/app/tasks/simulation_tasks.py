"""Tarefa Celery: corre uma simulação Monte Carlo em background.

Cada execução cria o seu próprio engine SQLAlchemy assíncrono (com
`NullPool`) dentro de um `asyncio.run()` novo — ver justificação
arquitetural completa na resposta do Módulo 8: reutilizar um pool de
ligações entre execuções de tarefas Celery (cada uma com o seu próprio
event loop) causa erros de "connection attached to a different loop".
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.cache.redis_client import get_redis_client
from app.cache.simulation_cache import SimulationResultCache
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import SIMULATION_DURATION_SECONDS, SIMULATIONS_TOTAL
from app.repositories.exceptions import EntityNotFoundError
from app.repositories.lookup_repository import LookupRepository
from app.repositories.match_repository import MatchRepository
from app.repositories.player_repository import PlayerRepository
from app.repositories.simulation_repository import SimulationRepository
from app.services.player_stats_service import PlayerStatsService
from app.simulation.estimation import estimate_serve_win_probability
from app.simulation.monte_carlo import MonteCarloMatchSimulator
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)


def _run_coroutine_in_new_thread(coro) -> None:
    """Corre uma coroutine até ao fim, numa thread nova com o seu próprio event loop.

    Mais robusto do que `asyncio.run()` direto: `asyncio.run()` falha
    com `RuntimeError` se já houver um event loop em execução na thread
    chamadora — o que acontece, por exemplo, em modo `task_always_eager`
    dentro de um teste assíncrono (o `.delay()` executa a tarefa
    sincronamente dentro do loop do próprio teste). Uma thread nova
    nunca tem um loop já a correr, pelo que este padrão funciona tanto
    num worker Celery real (processo separado, sem loop) como em modo
    eager dentro de qualquer código já assíncrono.
    """
    exception_holder: list[BaseException] = []

    def _target() -> None:
        try:
            asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - repropagado abaixo
            exception_holder.append(exc)

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join()

    if exception_holder:
        raise exception_holder[0]


def _make_session_factory():
    """Cria um engine assíncrono efémero (NullPool), só para esta execução."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return engine, async_sessionmaker(bind=engine, expire_on_commit=False)


async def _run_simulation_async(simulation_id: str) -> None:
    engine, session_factory = _make_session_factory()
    started_at = time.perf_counter()
    log = logger.bind(simulation_id=simulation_id)
    try:
        async with session_factory() as session:
            simulation_repo = SimulationRepository(session)
            simulation = await simulation_repo.get_by_id_or_raise(uuid.UUID(simulation_id))

            await simulation_repo.mark_running(simulation)
            await session.commit()
            log.info(
                "simulation_started",
                player1_id=str(simulation.player1_id),
                player2_id=str(simulation.player2_id),
                iterations=simulation.iterations,
                best_of=simulation.best_of,
            )

            player_repo = PlayerRepository(session)
            match_repo = MatchRepository(session)
            lookup_repo = LookupRepository(session)
            stats_service = PlayerStatsService(player_repo, match_repo)

            surface = await lookup_repo.get_surface(simulation.surface_id)
            if surface is None:
                raise EntityNotFoundError("Surface", simulation.surface_id)

            p1_stats = await stats_service.get_surface_stats(
                simulation.player1_id, simulation.surface_id
            )
            p2_stats = await stats_service.get_surface_stats(
                simulation.player2_id, simulation.surface_id
            )
            p1_prob = estimate_serve_win_probability(p1_stats)
            p2_prob = estimate_serve_win_probability(p2_stats)

            simulator = MonteCarloMatchSimulator(
                p1_prob, p2_prob, best_of=simulation.best_of
            )
            result = simulator.run(simulation.iterations)

            # Grava em cache antes de persistir o estado `completed` — um
            # pedido idêntico que chegue logo a seguir (ainda antes deste
            # `commit()`) já pode aproveitar o resultado, sem esperar pela
            # BD. Fail-open: `SimulationResultCache.set` nunca levanta em
            # caso de falha do Redis (ver docstring da classe).
            settings = get_settings()
            cache = SimulationResultCache(
                get_redis_client(), ttl_seconds=settings.simulation_cache_ttl_seconds
            )
            cache_key = SimulationResultCache.build_key(
                player1_id=simulation.player1_id,
                player2_id=simulation.player2_id,
                surface_id=simulation.surface_id,
                best_of=simulation.best_of,
                iterations=simulation.iterations,
            )
            await cache.set(cache_key, result)

            await simulation_repo.mark_completed(
                simulation,
                player1_win_probability=result.player1_win_probability,
                confidence_interval_lower=result.confidence_interval_lower,
                confidence_interval_upper=result.confidence_interval_upper,
                sets_won_distribution=result.sets_won_distribution,
                avg_match_duration_minutes=result.avg_match_duration_minutes,
            )
            await session.commit()

            duration_seconds = time.perf_counter() - started_at
            SIMULATION_DURATION_SECONDS.observe(duration_seconds)
            SIMULATIONS_TOTAL.labels(status="completed").inc()
            log.info(
                "simulation_completed",
                duration_seconds=round(duration_seconds, 4),
                player1_win_probability=result.player1_win_probability,
            )
    except Exception as exc:  # noqa: BLE001 - ver justificação abaixo
        # Captura deliberadamente ampla: qualquer falha durante a
        # simulação (jogador removido entretanto, erro de dados, bug)
        # deve marcar a simulação como `failed` de forma visível ao
        # cliente via `GET /simulations/{id}`, nunca desaparecer
        # silenciosamente numa tarefa Celery sem resultado.
        SIMULATIONS_TOTAL.labels(status="failed").inc()
        log.error("simulation_failed", error=str(exc), exc_info=True)
        await _mark_failed_best_effort(simulation_id, str(exc))
        raise
    finally:
        await engine.dispose()


async def _mark_failed_best_effort(simulation_id: str, error_message: str) -> None:
    """Marca a simulação como `failed`, numa transação/sessão à parte.

    Sessão nova e independente da que falhou — se a sessão original
    ficou num estado inconsistente (rollback pendente), não a reaproveita
    para escrever o estado de falha.
    """
    engine, session_factory = _make_session_factory()
    try:
        async with session_factory() as session:
            simulation_repo = SimulationRepository(session)
            simulation = await simulation_repo.get_by_id(uuid.UUID(simulation_id))
            if simulation is not None:
                await simulation_repo.mark_failed(simulation, error_message=error_message)
                await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="simulations.run_simulation", bind=True, max_retries=0)
def run_simulation_task(self, simulation_id: str) -> None:
    """Ponto de entrada síncrono da tarefa Celery (invocado por `.delay()`)."""
    _run_coroutine_in_new_thread(_run_simulation_async(simulation_id))
