"""Objeto de resultado do motor de simulação Monte Carlo."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MonteCarloSimulationResult:
    """Resultado agregado de uma simulação Monte Carlo de um jogo.

    Espelha diretamente os campos de `simulation_results` na especificação
    de BD e da resposta `GET /api/v1/simulations/{id}` na especificação
    da API REST.
    """

    player1_win_probability: float
    confidence_interval_lower: float
    confidence_interval_upper: float
    sets_won_distribution: dict[str, float]
    avg_match_duration_minutes: float
    iterations: int
