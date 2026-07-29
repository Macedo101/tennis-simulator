"""Estimativa da probabilidade de ganhar um ponto ao serviço.

Ponte entre o `PlayerStatsService` (Módulo 3, que agrega estatísticas
por superfície) e o `MonteCarloMatchSimulator` (Módulo 4, que espera
uma única probabilidade por ponto ao serviço).
"""
from __future__ import annotations

from app.services.dto import SurfaceStatsResult

#: Probabilidade de ponto ao serviço assumida quando não há estatísticas
#: suficientes (jogador novo, sem jogos completos registados na
#: superfície). Baseada em médias publicamente conhecidas do circuito
#: ATP (~62% de pontos ganhos ao serviço) — uma estimativa neutra e
#: documentada, não um valor arbitrário escondido.
DEFAULT_SERVE_WIN_PROBABILITY = 0.62

# Limites de segurança: o motor Monte Carlo rejeita probabilidades
# exatamente em 0 ou 1 (ver `MonteCarloMatchSimulator.__init__`), pelo
# que qualquer estimativa é sempre mantida estritamente dentro de (0, 1).
_MIN_PROBABILITY = 0.01
_MAX_PROBABILITY = 0.99


def estimate_serve_win_probability(
    stats: SurfaceStatsResult, *, fallback: float = DEFAULT_SERVE_WIN_PROBABILITY
) -> float:
    """Estima P(ganhar um ponto ao serviço) a partir de estatísticas agregadas.

    Fórmula: probabilidade ponderada entre o resultado do primeiro
    serviço (quando entra) e do segundo serviço (quando o primeiro
    falha) — a forma padrão de decompor a taxa de pontos ganhos ao
    serviço em ténis:

        P = P(1º serviço entra) * P(ganha o ponto | 1º serviço)
          + P(1º serviço falha) * P(ganha o ponto | 2º serviço)

    Se faltar qualquer uma das três estatísticas de origem, devolve
    `fallback` — mais honesto do que inventar um valor a partir de
    dados parciais.
    """
    if (
        stats.avg_first_serve_pct is None
        or stats.avg_first_serve_points_won_pct is None
        or stats.avg_second_serve_points_won_pct is None
    ):
        return fallback

    first_serve_in = stats.avg_first_serve_pct / 100.0
    first_serve_win = stats.avg_first_serve_points_won_pct / 100.0
    second_serve_win = stats.avg_second_serve_points_won_pct / 100.0

    probability = first_serve_in * first_serve_win + (1 - first_serve_in) * second_serve_win
    return min(max(probability, _MIN_PROBABILITY), _MAX_PROBABILITY)
