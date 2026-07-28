"""Engenharia de features para o modelo preditivo.

`FeatureVector` é construído a partir dos DTOs já calculados pelo
`PlayerStatsService` (Módulo 3) — o modelo nunca acede à BD/repositórios
diretamente. Todas as features são diferenças relativas
(`jogador1 - jogador2`), o que torna o modelo simetricamente correto
por construção (ver justificação arquitetural).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.dto import (
    HeadToHeadSummaryResult,
    RecentFormResult,
    SurfaceStatsResult,
)

#: Ordem canónica das colunas de features — usada tanto no treino como
#: na previsão, para garantir que o array numérico enviado ao modelo
#: tem sempre o mesmo significado por posição.
FEATURE_NAMES: tuple[str, ...] = (
    "rank_diff",
    "points_diff",
    "recent_form_win_rate_diff",
    "surface_win_rate_diff",
    "surface_first_serve_pct_diff",
    "h2h_win_rate_diff",
)


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """Vetor de features para um jogo (sempre jogador1 relativo a jogador2)."""

    rank_diff: float
    points_diff: float
    recent_form_win_rate_diff: float
    surface_win_rate_diff: float
    surface_first_serve_pct_diff: float
    h2h_win_rate_diff: float

    def to_array(self) -> list[float]:
        """Converte para lista ordenada segundo `FEATURE_NAMES`."""
        return [
            self.rank_diff,
            self.points_diff,
            self.recent_form_win_rate_diff,
            self.surface_win_rate_diff,
            self.surface_first_serve_pct_diff,
            self.h2h_win_rate_diff,
        ]


def build_feature_vector(
    *,
    player1_rank: int,
    player2_rank: int,
    player1_points: int,
    player2_points: int,
    player1_form: RecentFormResult,
    player2_form: RecentFormResult,
    player1_surface_stats: SurfaceStatsResult,
    player2_surface_stats: SurfaceStatsResult,
    h2h: HeadToHeadSummaryResult,
) -> FeatureVector:
    """Constrói o `FeatureVector` de um jogo a partir dos DTOs do Módulo 3.

    Nota sobre sinal: `rank_diff = player2_rank - player1_rank` (não o
    inverso) — um ranking mais BAIXO é melhor no ténis (nº 1 é o
    melhor), pelo que esta subtração garante que valores mais altos de
    `rank_diff` favorecem sempre o jogador 1, consistente com o sinal
    das restantes features (todas "maior = melhor para o jogador 1").
    """
    h2h_total = h2h.total_matches
    h2h_win_rate_diff = (
        (h2h.player1_wins - h2h.player2_wins) / h2h_total if h2h_total > 0 else 0.0
    )

    surface_serve_pct_diff = _safe_diff(
        player1_surface_stats.avg_first_serve_pct,
        player2_surface_stats.avg_first_serve_pct,
    )

    return FeatureVector(
        rank_diff=float(player2_rank - player1_rank),
        points_diff=float(player1_points - player2_points),
        recent_form_win_rate_diff=player1_form.win_rate - player2_form.win_rate,
        surface_win_rate_diff=(
            player1_surface_stats.win_rate - player2_surface_stats.win_rate
        ),
        surface_first_serve_pct_diff=surface_serve_pct_diff,
        h2h_win_rate_diff=h2h_win_rate_diff,
    )


def _safe_diff(a: float | None, b: float | None) -> float:
    """Diferença entre dois valores opcionais; `0.0` se algum faltar.

    Zero é a escolha correta aqui (não `None`/NaN): representa "sem
    evidência de vantagem", que é semanticamente o que significa faltar
    dados suficientes de uma superfície — não deve empurrar o modelo
    para nenhum dos lados.
    """
    if a is None or b is None:
        return 0.0
    return a - b
