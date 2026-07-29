"""Gerador de dataset sintético para validar o pipeline de treino.

Não existem dados históricos reais ATP/WTA neste ambiente. Este módulo
gera um dataset sintético a partir de uma função de probabilidade
conhecida (`true_win_probability`), o que permite testar que o
pipeline de treino recupera corretamente um sinal verdadeiro conhecido
— uma propriedade que não seria verificável de forma determinística
com dados reais em teste automatizado.

Em produção, este módulo é substituído por um pipeline de ETL que
carrega features reais a partir da BD (via `PlayerStatsService`) e
resultados históricos reais de `matches.winner_id`.
"""
from __future__ import annotations

import numpy as np

from app.ml.features import FEATURE_NAMES

#: Pesos "verdadeiros" usados para gerar os rótulos sintéticos — cada
#: feature contribui logisticamente para a probabilidade de vitória do
#: jogador 1. Usados só para gerar dados de teste, nunca no modelo real.
_TRUE_WEIGHTS = np.array([0.015, 0.0004, 2.2, 1.8, 0.02, 1.1])
_TRUE_BIAS = 0.0


def true_win_probability(features: np.ndarray) -> np.ndarray:
    """Probabilidade "verdadeira" (sigmoid) usada para gerar rótulos sintéticos."""
    logits = features @ _TRUE_WEIGHTS + _TRUE_BIAS
    return 1.0 / (1.0 + np.exp(-logits))


def generate_synthetic_dataset(
    n_samples: int, *, seed: int = 0
) -> tuple[np.ndarray, np.ndarray]:
    """Gera `(X, y)` sintéticos com sinal conhecido.

    `X` tem `n_samples` linhas e `len(FEATURE_NAMES)` colunas, com
    valores amostrados de distribuições plausíveis para cada feature
    (diferenças de ranking, forma, etc.). `y` é amostrado de uma
    Bernoulli com probabilidade `true_win_probability(X)`.
    """
    rng = np.random.default_rng(seed)
    n_features = len(FEATURE_NAMES)

    rank_diff = rng.normal(0, 30, n_samples)
    points_diff = rng.normal(0, 800, n_samples)
    form_diff = rng.normal(0, 0.25, n_samples)
    surface_win_rate_diff = rng.normal(0, 0.25, n_samples)
    surface_serve_pct_diff = rng.normal(0, 8, n_samples)
    h2h_diff = rng.normal(0, 0.4, n_samples)

    X = np.column_stack(
        [
            rank_diff,
            points_diff,
            form_diff,
            surface_win_rate_diff,
            surface_serve_pct_diff,
            h2h_diff,
        ]
    )
    assert X.shape == (n_samples, n_features)

    probabilities = true_win_probability(X)
    y = rng.binomial(1, probabilities)

    return X, y
