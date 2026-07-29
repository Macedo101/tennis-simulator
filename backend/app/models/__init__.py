"""Regista todos os modelos ORM em Base.metadata.

Importar este módulo garante que todas as classes de modelo são
carregadas antes de qualquer uso de Base.metadata (Alembic autogenerate,
create_all em testes, resolução de relationship() com strings
forward-reference).
"""
from app.models.auth import RefreshToken, User
from app.models.lookup import Country, Surface
from app.models.match import Match, MatchSet, MatchStatistics
from app.models.player import Player, PlayerRanking
from app.models.simulation import Simulation
from app.models.tournament import Tournament, TournamentEdition

__all__ = [
    "Country",
    "Surface",
    "Player",
    "PlayerRanking",
    "Tournament",
    "TournamentEdition",
    "Match",
    "MatchSet",
    "MatchStatistics",
    "User",
    "RefreshToken",
    "Simulation",
]
