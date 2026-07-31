"""Motor de simulação Monte Carlo — ponto a ponto, vetorizado com NumPy.

Cada iteração da simulação representa um jogo completo simulado de
forma independente. Todas as N iterações avançam em paralelo (arrays
NumPy de forma `(n,)`), ronda a ronda de pontos, o que torna a
simulação de 100.000+ iterações ordens de magnitude mais rápida do que
um loop Python puro por iteração.

Hierarquia de simulação (de baixo para cima):
    ponto -> jogo de serviço (`simulate_service_game`)
    ponto -> tie-break (`simulate_tiebreak`)
    jogos/tie-break -> set (`simulate_set`)
    sets -> jogo completo (`MonteCarloMatchSimulator.run`)
"""
from __future__ import annotations

import numpy as np

from app.simulation.dto import MonteCarloSimulationResult

# Segundos médios por ponto disputado, usado apenas para estimar a
# duração média do jogo — baseado em médias publicamente conhecidas do
# circuito ATP (~35-40s incluindo tempo entre pontos). É uma estimativa
# de engenharia explicitamente assumida, não uma medição real.
_AVG_SECONDS_PER_POINT = 37.0

# Nível de confiança do intervalo devolvido (95%).
_Z_SCORE_95 = 1.959963985


def simulate_service_game(
    server_win_prob: np.ndarray,
    rng: np.random.Generator,
    *,
    max_rounds: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Simula um jogo de serviço, ponto a ponto, para N iterações em paralelo.

    Parameters
    ----------
    server_win_prob:
        Array `(n,)` com a probabilidade do jogador ao serviço ganhar
        cada ponto, uma por iteração.
    max_rounds:
        Limite de segurança de pontos disputados por jogo. Um jogo de
        ténis pode em teoria nunca terminar (deuce indefinido); 200
        pontos é um limite que a probabilidade de ser atingido é
        astronomicamente pequena mesmo com p=0.5, protegendo apenas
        contra um loop sem fim — não altera o resultado estatístico.

    Returns
    -------
    (server_wins, points_played):
        `server_wins` — array booleano `(n,)`, `True` onde o jogador ao
        serviço venceu o jogo.
        `points_played` — array inteiro `(n,)` com o nº de pontos
        disputados em cada jogo (usado para estimar duração).
    """
    n = server_win_prob.shape[0]
    server_points = np.zeros(n, dtype=np.int32)
    returner_points = np.zeros(n, dtype=np.int32)
    decided = np.zeros(n, dtype=bool)
    server_wins = np.zeros(n, dtype=bool)
    points_played = np.zeros(n, dtype=np.int32)

    for _ in range(max_rounds):
        if decided.all():
            break
        active = ~decided
        draws = rng.random(n) < server_win_prob
        server_points += active & draws
        returner_points += active & ~draws
        points_played += active

        lead = server_points - returner_points
        game_over = ((server_points >= 4) | (returner_points >= 4)) & (
            np.abs(lead) >= 2
        )
        newly_decided = active & game_over
        server_wins[newly_decided] = lead[newly_decided] > 0
        decided |= game_over

    return server_wins, points_played


def simulate_tiebreak(
    p1_serve_prob: np.ndarray,
    p2_serve_prob: np.ndarray,
    starting_server_is_p1: np.ndarray,
    rng: np.random.Generator,
    *,
    target_points: int = 7,
    max_rounds: int = 400,
) -> tuple[np.ndarray, np.ndarray]:
    """Simula um tie-break (7 pontos, vantagem mínima de 2), ponto a ponto.

    Respeita o padrão real de alternância de serviço num tie-break:
    o primeiro ponto é servido por `starting_server`, os dois pontos
    seguintes pelo adversário, os dois seguintes de volta ao primeiro
    servidor, e assim sucessivamente — calculado vetorialmente por
    aritmética modular sobre o índice do ponto.

    Returns
    -------
    (player1_wins_tiebreak, points_played)
    """
    n = p1_serve_prob.shape[0]
    p1_points = np.zeros(n, dtype=np.int32)
    p2_points = np.zeros(n, dtype=np.int32)
    point_index = np.zeros(n, dtype=np.int32)
    decided = np.zeros(n, dtype=bool)
    p1_wins = np.zeros(n, dtype=bool)

    for _ in range(max_rounds):
        if decided.all():
            break
        active = ~decided

        # Determina quem serve este ponto (ver docstring para o padrão).
        block = np.maximum(point_index - 1, 0) // 2
        server_is_p1 = np.where(
            point_index == 0,
            starting_server_is_p1,
            np.where(block % 2 == 1, starting_server_is_p1, ~starting_server_is_p1),
        )
        server_prob = np.where(server_is_p1, p1_serve_prob, p2_serve_prob)
        server_wins_point = rng.random(n) < server_prob
        p1_wins_point = np.where(server_is_p1, server_wins_point, ~server_wins_point)

        p1_points += active & p1_wins_point
        p2_points += active & ~p1_wins_point
        point_index += active.astype(np.int32)

        lead = p1_points - p2_points
        tb_over = (
            (p1_points >= target_points) | (p2_points >= target_points)
        ) & (np.abs(lead) >= 2)
        newly_decided = active & tb_over
        p1_wins[newly_decided] = lead[newly_decided] > 0
        decided |= tb_over

    return p1_wins, point_index


def simulate_set(
    p1_serve_prob: np.ndarray,
    p2_serve_prob: np.ndarray,
    starting_server_is_p1: np.ndarray,
    rng: np.random.Generator,
    *,
    max_games: int = 40,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Simula um set completo (jogos + tie-break se necessário a 6-6).

    Returns
    -------
    (p1_games, p2_games, player1_wins_set, points_played)
    """
    n = p1_serve_prob.shape[0]
    p1_games = np.zeros(n, dtype=np.int32)
    p2_games = np.zeros(n, dtype=np.int32)
    decided = np.zeros(n, dtype=bool)
    p1_wins_set = np.zeros(n, dtype=bool)
    points_played = np.zeros(n, dtype=np.int32)
    server_is_p1 = starting_server_is_p1.copy()

    for _ in range(max_games):
        if decided.all():
            break
        active = ~decided
        need_tiebreak = active & (p1_games == 6) & (p2_games == 6)
        need_regular = active & ~need_tiebreak

        # Jogo de serviço "normal" — computado para todas as iterações,
        # mas só aplicado (via máscara) às que efetivamente precisam dele.
        server_prob = np.where(server_is_p1, p1_serve_prob, p2_serve_prob)
        server_wins_game, regular_points = simulate_service_game(server_prob, rng)
        p1_wins_regular = np.where(server_is_p1, server_wins_game, ~server_wins_game)

        p1_games += (need_regular & p1_wins_regular).astype(np.int32)
        p2_games += (need_regular & ~p1_wins_regular).astype(np.int32)
        points_played += np.where(need_regular, regular_points, 0)
        server_is_p1 = np.where(need_regular, ~server_is_p1, server_is_p1)

        # Tie-break — resolvido de imediato (decide sempre o set).
        tb_p1_wins, tb_points = simulate_tiebreak(
            p1_serve_prob, p2_serve_prob, server_is_p1, rng
        )
        p1_games += (need_tiebreak & tb_p1_wins).astype(np.int32)
        p2_games += (need_tiebreak & ~tb_p1_wins).astype(np.int32)
        points_played += np.where(need_tiebreak, tb_points, 0)

        lead = p1_games - p2_games
        set_over = need_tiebreak | (
            ((p1_games >= 6) | (p2_games >= 6)) & (np.abs(lead) >= 2)
        )
        newly_decided = active & set_over
        p1_wins_set[newly_decided] = (p1_games > p2_games)[newly_decided]
        decided |= set_over

    return p1_games, p2_games, p1_wins_set, points_played


class MonteCarloMatchSimulator:
    """Simulador Monte Carlo de um jogo completo entre dois jogadores.

    Recebe as probabilidades de ganhar um ponto ao serviço de cada
    jogador (input tipicamente derivado das estatísticas por superfície
    calculadas pelo `PlayerStatsService`, Módulo 3) e simula o jogo
    inteiro, ponto a ponto, `iterations` vezes.
    """

    def __init__(
        self,
        player1_serve_win_prob: float,
        player2_serve_win_prob: float,
        best_of: int,
        *,
        seed: int | None = None,
    ) -> None:
        for name, value in (
            ("player1_serve_win_prob", player1_serve_win_prob),
            ("player2_serve_win_prob", player2_serve_win_prob),
        ):
            if not 0.0 < value < 1.0:
                raise ValueError(f"{name} deve estar em (0, 1), recebeu {value}")
        if best_of not in (3, 5):
            raise ValueError(f"best_of deve ser 3 ou 5, recebeu {best_of}")

        self._p1 = player1_serve_win_prob
        self._p2 = player2_serve_win_prob
        self._best_of = best_of
        self._sets_to_win = best_of // 2 + 1
        self._rng = np.random.default_rng(seed)

    def run(self, iterations: int) -> MonteCarloSimulationResult:
        """Corre `iterations` simulações completas do jogo e agrega o resultado."""
        if not 1_000 <= iterations <= 1_000_000:
            raise ValueError(
                f"iterations deve estar entre 1000 e 1000000, recebeu {iterations}"
            )

        n = iterations
        p1_prob = np.full(n, self._p1, dtype=np.float64)
        p2_prob = np.full(n, self._p2, dtype=np.float64)

        p1_sets_won = np.zeros(n, dtype=np.int32)
        p2_sets_won = np.zeros(n, dtype=np.int32)
        match_decided = np.zeros(n, dtype=bool)
        match_points = np.zeros(n, dtype=np.int64)
        # Servidor inicial do 1º set: alternado aleatoriamente por
        # iteração para não enviesar sistematicamente a favor de um
        # jogador (em produção seria conhecido a partir do sorteio real).
        server_is_p1 = self._rng.random(n) < 0.5

        max_sets = self._best_of
        for _ in range(max_sets):
            if match_decided.all():
                break
            _p1_games, _p2_games, p1_wins_set, set_points = simulate_set(
                p1_prob, p2_prob, server_is_p1, self._rng
            )
            active = ~match_decided
            p1_sets_won += (active & p1_wins_set).astype(np.int32)
            p2_sets_won += (active & ~p1_wins_set).astype(np.int32)
            match_points += np.where(active, set_points, 0)

            match_over = (p1_sets_won >= self._sets_to_win) | (
                p2_sets_won >= self._sets_to_win
            )
            match_decided |= match_over
            # Alterna quem serve o primeiro jogo do set seguinte
            # (aproximação documentada — a regra exata depende de quem
            # recebeu o último jogo do set anterior; não afeta
            # materialmente a distribuição estatística do resultado).
            server_is_p1 = np.where(active, ~server_is_p1, server_is_p1)

        return self._aggregate(p1_sets_won, p2_sets_won, match_points, n)

    def _aggregate(
        self,
        p1_sets_won: np.ndarray,
        p2_sets_won: np.ndarray,
        match_points: np.ndarray,
        iterations: int,
    ) -> MonteCarloSimulationResult:
        player1_wins = p1_sets_won > p2_sets_won
        win_count = int(player1_wins.sum())
        p_hat = win_count / iterations

        margin = _Z_SCORE_95 * np.sqrt(p_hat * (1 - p_hat) / iterations)
        ci_lower = max(0.0, p_hat - margin)
        ci_upper = min(1.0, p_hat + margin)

        sets_won_distribution = self._sets_won_distribution(p1_sets_won, p2_sets_won, iterations)

        avg_points = float(match_points.mean())
        avg_duration_minutes = round(
            avg_points * _AVG_SECONDS_PER_POINT / 60.0, 1
        )

        return MonteCarloSimulationResult(
            player1_win_probability=round(p_hat, 4),
            confidence_interval_lower=round(ci_lower, 4),
            confidence_interval_upper=round(ci_upper, 4),
            sets_won_distribution=sets_won_distribution,
            avg_match_duration_minutes=avg_duration_minutes,
            iterations=iterations,
        )

    def _sets_won_distribution(
        self, p1_sets_won: np.ndarray, p2_sets_won: np.ndarray, iterations: int
    ) -> dict[str, float]:
        """Distribuição de placares finais (ex.: '3-1', '2-3'), como fração.

        Formato consistente com o exemplo `sets_won_distribution` da
        especificação da API REST.
        """
        distribution: dict[str, float] = {}
        for p1, p2 in zip(p1_sets_won.tolist(), p2_sets_won.tolist(), strict=True):
            key = f"{p1}-{p2}"
            distribution[key] = distribution.get(key, 0) + 1
        return {k: round(v / iterations, 4) for k, v in sorted(distribution.items())}
