"""Testes do motor de simulação Monte Carlo.

Inclui validação estatística contra a fórmula analítica fechada da
probabilidade de vencer um jogo de serviço — a forma correta de testar
uma simulação Monte Carlo não é só "corre sem rebentar", é confirmar
que converge para o valor teórico conhecido.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.simulation.monte_carlo import (
    MonteCarloMatchSimulator,
    simulate_service_game,
    simulate_set,
    simulate_tiebreak,
)


def _analytic_service_game_win_probability(p: float) -> float:
    """Probabilidade fechada de ganhar um jogo de serviço, dado p por ponto.

    Derivação: soma dos caminhos que terminam antes de 3-3 (4-0, 4-1,
    4-2), mais o caminho que passa por deuce (3-3), cuja probabilidade
    de vitória a partir daí é `d = p^2 / (1 - 2pq)` (random walk clássico
    de deuce). Usado só em teste, como "ground truth" independente do
    código de simulação — não faz parte do motor em produção.
    """
    q = 1 - p
    p_before_deuce = p**4 * (1 + 4 * q + 10 * q**2)
    reach_deuce = 20 * p**3 * q**3
    d = p**2 / (1 - 2 * p * q)
    return p_before_deuce + reach_deuce * d


@pytest.mark.parametrize("p", [0.55, 0.60, 0.65, 0.70])
def test_simulate_service_game_matches_analytic_formula(p: float) -> None:
    n = 200_000
    rng = np.random.default_rng(42)
    server_prob = np.full(n, p)

    server_wins, points_played = simulate_service_game(server_prob, rng)

    empirical = server_wins.mean()
    expected = _analytic_service_game_win_probability(p)

    assert empirical == pytest.approx(expected, abs=0.01)
    assert (points_played >= 4).all()


def test_simulate_service_game_deterministic_extremes() -> None:
    rng = np.random.default_rng(1)
    n = 1_000

    always_server = simulate_service_game(np.full(n, 0.999999), rng)[0]
    assert always_server.all()

    never_server = simulate_service_game(np.full(n, 0.000001), rng)[0]
    assert not never_server.any()


def test_simulate_tiebreak_symmetric_players_near_fifty_fifty() -> None:
    n = 100_000
    rng = np.random.default_rng(7)
    p1 = np.full(n, 0.65)
    p2 = np.full(n, 0.65)
    starting_server_is_p1 = np.full(n, True)

    p1_wins, points_played = simulate_tiebreak(p1, p2, starting_server_is_p1, rng)

    assert p1_wins.mean() == pytest.approx(0.5, abs=0.02)
    assert (points_played >= 7).all()


def test_simulate_tiebreak_skewed_players_favor_stronger() -> None:
    n = 20_000
    rng = np.random.default_rng(3)
    p1 = np.full(n, 0.85)
    p2 = np.full(n, 0.30)
    starting_server_is_p1 = np.full(n, True)

    p1_wins, _ = simulate_tiebreak(p1, p2, starting_server_is_p1, rng)

    assert p1_wins.mean() > 0.9


def test_simulate_set_symmetric_players_near_fifty_fifty() -> None:
    n = 50_000
    rng = np.random.default_rng(11)
    p1 = np.full(n, 0.62)
    p2 = np.full(n, 0.62)
    starting_server = np.full(n, True)

    p1_games, p2_games, p1_wins_set, points_played = simulate_set(
        p1, p2, starting_server, rng
    )

    assert p1_wins_set.mean() == pytest.approx(0.5, abs=0.03)
    assert (p1_games.max() <= 7) and (p2_games.max() <= 7)
    assert (points_played > 0).all()


class TestMonteCarloMatchSimulator:
    def test_rejects_out_of_range_probabilities(self) -> None:
        with pytest.raises(ValueError, match="player1_serve_win_prob"):
            MonteCarloMatchSimulator(1.5, 0.5, best_of=3)

        with pytest.raises(ValueError, match="player2_serve_win_prob"):
            MonteCarloMatchSimulator(0.5, 0.0, best_of=3)

    def test_rejects_invalid_best_of(self) -> None:
        with pytest.raises(ValueError, match="best_of"):
            MonteCarloMatchSimulator(0.6, 0.6, best_of=4)

    def test_rejects_iterations_out_of_bounds(self) -> None:
        simulator = MonteCarloMatchSimulator(0.6, 0.6, best_of=3, seed=1)
        with pytest.raises(ValueError, match="iterations"):
            simulator.run(iterations=500)
        with pytest.raises(ValueError, match="iterations"):
            simulator.run(iterations=2_000_000)

    def test_symmetric_players_win_probability_near_fifty_fifty(self) -> None:
        simulator = MonteCarloMatchSimulator(0.65, 0.65, best_of=5, seed=99)

        result = simulator.run(iterations=30_000)

        assert result.player1_win_probability == pytest.approx(0.5, abs=0.03)
        assert result.confidence_interval_lower <= result.player1_win_probability
        assert result.confidence_interval_upper >= result.player1_win_probability

    def test_dominant_player_wins_overwhelming_majority(self) -> None:
        simulator = MonteCarloMatchSimulator(0.85, 0.35, best_of=3, seed=5)

        result = simulator.run(iterations=10_000)

        assert result.player1_win_probability > 0.9

    def test_sets_won_distribution_sums_to_one(self) -> None:
        simulator = MonteCarloMatchSimulator(0.6, 0.55, best_of=5, seed=2)

        result = simulator.run(iterations=5_000)

        total = sum(result.sets_won_distribution.values())
        assert total == pytest.approx(1.0, abs=1e-6)
        # best_of=5: só placares válidos são 3-0,3-1,3-2,0-3,1-3,2-3
        assert all(
            key in {"3-0", "3-1", "3-2", "0-3", "1-3", "2-3"}
            for key in result.sets_won_distribution
        )

    def test_best_of_three_only_produces_valid_scorelines(self) -> None:
        simulator = MonteCarloMatchSimulator(0.6, 0.55, best_of=3, seed=8)

        result = simulator.run(iterations=5_000)

        assert all(
            key in {"2-0", "2-1", "0-2", "1-2"}
            for key in result.sets_won_distribution
        )

    def test_avg_match_duration_is_positive_and_reasonable(self) -> None:
        simulator = MonteCarloMatchSimulator(0.6, 0.6, best_of=3, seed=4)

        result = simulator.run(iterations=5_000)

        # Um jogo de ténis best-of-3 razoável dura tipicamente entre
        # ~40 minutos e ~3 horas.
        assert 30.0 < result.avg_match_duration_minutes < 200.0

    def test_same_seed_is_reproducible(self) -> None:
        result_a = MonteCarloMatchSimulator(0.6, 0.55, best_of=3, seed=123).run(5_000)
        result_b = MonteCarloMatchSimulator(0.6, 0.55, best_of=3, seed=123).run(5_000)

        assert result_a.player1_win_probability == result_b.player1_win_probability
        assert result_a.sets_won_distribution == result_b.sets_won_distribution
