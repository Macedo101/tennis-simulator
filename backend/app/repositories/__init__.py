"""Camada de repositórios — abstrai o acesso a dados sobre SQLAlchemy."""
from app.repositories.base import BaseRepository
from app.repositories.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    RepositoryError,
)
from app.repositories.lookup_repository import LookupRepository
from app.repositories.match_repository import MatchRepository
from app.repositories.player_repository import PlayerRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.simulation_repository import SimulationRepository
from app.repositories.tournament_repository import TournamentRepository
from app.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "RepositoryError",
    "EntityNotFoundError",
    "DuplicateEntityError",
    "LookupRepository",
    "MatchRepository",
    "PlayerRepository",
    "TournamentRepository",
    "UserRepository",
    "RefreshTokenRepository",
    "SimulationRepository",
]
