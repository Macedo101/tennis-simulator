"""Dependências FastAPI: liga a sessão de BD aos repositórios e serviços.

Cadeia de injeção: `get_db_session` (Módulo 1) -> repositórios
(Módulo 2) -> serviços (Módulo 3). Um router nunca deve instanciar um
repositório diretamente — pede sempre a dependência já montada.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.exceptions import RateLimitExceededError
from app.cache.rate_limiter import RateLimiter
from app.cache.redis_client import get_redis_client
from app.cache.simulation_cache import SimulationResultCache
from app.core.config import get_settings
from app.db.base import get_db_session
from app.ml.model import MatchOutcomeModel, ModelNotFittedError
from app.models.auth import User
from app.repositories.lookup_repository import LookupRepository
from app.repositories.match_repository import MatchRepository
from app.repositories.player_repository import PlayerRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.simulation_repository import SimulationRepository
from app.repositories.tournament_repository import TournamentRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import (
    AuthService,
    InsufficientPermissionsError,
)
from app.services.player_stats_service import PlayerStatsService

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_player_repository(session: DbSession) -> PlayerRepository:
    return PlayerRepository(session)


def get_match_repository(session: DbSession) -> MatchRepository:
    return MatchRepository(session)


def get_tournament_repository(session: DbSession) -> TournamentRepository:
    return TournamentRepository(session)


def get_lookup_repository(session: DbSession) -> LookupRepository:
    return LookupRepository(session)


def get_simulation_repository(session: DbSession) -> SimulationRepository:
    return SimulationRepository(session)


PlayerRepo = Annotated[PlayerRepository, Depends(get_player_repository)]
MatchRepo = Annotated[MatchRepository, Depends(get_match_repository)]
TournamentRepo = Annotated[TournamentRepository, Depends(get_tournament_repository)]
LookupRepo = Annotated[LookupRepository, Depends(get_lookup_repository)]
SimulationRepo = Annotated[SimulationRepository, Depends(get_simulation_repository)]


def get_player_stats_service(
    player_repository: PlayerRepo, match_repository: MatchRepo
) -> PlayerStatsService:
    return PlayerStatsService(player_repository, match_repository)


PlayerStatsServiceDep = Annotated[PlayerStatsService, Depends(get_player_stats_service)]


def get_user_repository(session: DbSession) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: DbSession) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


UserRepo = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepo = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]


def get_auth_service(
    user_repository: UserRepo, refresh_token_repository: RefreshTokenRepo
) -> AuthService:
    return AuthService(user_repository, refresh_token_repository)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

# `tokenUrl` aponta para o endpoint de login real — usado apenas para o
# Swagger UI saber onde pedir o token pelo botão "Authorize"; a
# validação em si é sempre feita por `AuthService.get_current_user`.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(_oauth2_scheme)], auth_service: AuthServiceDep
) -> User:
    """Resolve o utilizador autenticado a partir do header `Authorization: Bearer`.

    `InvalidCredentialsError` (token ausente/inválido/expirado, ou
    utilizador entretanto apagado) é traduzida a `401` pelo handler
    global de erros (Módulo 6) — este dependency nunca devolve `None`
    nem deixa o pedido prosseguir sem um utilizador válido.
    """
    return await auth_service.get_current_user(token)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(current_user: CurrentUser) -> User:
    """Como `get_current_user`, mas exige `role == 'admin'`.

    Usado (ainda não neste módulo, mas já pronto) para proteger
    `/admin/*` — `Depends(require_admin)` em vez de repetir a
    verificação de `role` em cada handler administrativo.
    """
    if current_user.role != "admin":
        raise InsufficientPermissionsError("Esta operação requer privilégios de administrador.")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]


@lru_cache
def _load_model_cached(path: str) -> MatchOutcomeModel:
    """Carrega o modelo treinado do disco, em cache por processo.

    `lru_cache` evita desserializar o modelo (potencialmente pesado, um
    `XGBClassifier` calibrado) a cada pedido — carregado uma vez, mantido
    em memória para o resto do ciclo de vida do processo worker.
    """
    return MatchOutcomeModel.load(path)


def get_match_outcome_model() -> MatchOutcomeModel:
    """Dependency que fornece o modelo preditivo de produção já treinado.

    Levanta `ModelNotFittedError` (traduzido para `503` pelo handler
    global de erros) se ainda não existir um artefacto de modelo
    guardado em disco — situação esperada antes de existir um pipeline
    de treino agendado (Módulo 8/9), e mais honesto do que fingir uma
    previsão sem modelo real por trás.
    """
    settings = get_settings()
    model_path = Path(settings.ml_model_path)
    if not model_path.exists():
        raise ModelNotFittedError(
            f"Nenhum modelo treinado encontrado em '{model_path}'."
        )
    return _load_model_cached(str(model_path))


MatchOutcomeModelDep = Annotated[MatchOutcomeModel, Depends(get_match_outcome_model)]


def get_rate_limiter() -> RateLimiter:
    return RateLimiter(get_redis_client())


def get_simulation_cache() -> SimulationResultCache:
    settings = get_settings()
    return SimulationResultCache(
        get_redis_client(), ttl_seconds=settings.simulation_cache_ttl_seconds
    )


SimulationCacheDep = Annotated[SimulationResultCache, Depends(get_simulation_cache)]


async def enforce_simulation_rate_limit(
    current_user: CurrentUser,
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    """Limite dedicado de simulações (10/hora por utilizador).

    Adicional ao limite geral já imposto pelo `RateLimitMiddleware`
    (100/min) — este é mais apertado e específico deste endpoint, tal
    como especificado na API REST (secção `POST /simulations`), porque
    uma simulação é uma operação muito mais cara do que um `GET` normal.
    """
    settings = get_settings()
    result = await rate_limiter.check(
        f"simulations:{current_user.id}",
        limit=settings.rate_limit_simulations_per_hour,
        window_seconds=3600,
    )
    if not result.allowed:
        raise RateLimitExceededError(
            limit=result.limit, window_seconds=3600, reset_at=result.reset_at
        )
