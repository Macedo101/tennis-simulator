"""Modelo preditivo de resultado de jogo: baseline e produção, com
tracking de experimentação via MLflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import joblib
import mlflow
import mlflow.sklearn
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from xgboost import XGBClassifier

ModelType = Literal["baseline", "production"]

# Backend de tracking do MLflow: SQLite local (sem servidor).
# Nota: o backend de ficheiros simples ("file:./mlruns") entrou em modo
# de manutenção nas versões recentes do MLflow (>=3.x) — SQLite é agora
# o backend local recomendado, mantendo a mesma simplicidade operacional
# (nenhum servidor a gerir) exigida para um projeto de portfólio.
_MLFLOW_TRACKING_URI = f"sqlite:///{Path.cwd() / 'mlflow.db'}"
_EXPERIMENT_NAME = "tennis-match-outcome"


@dataclass(frozen=True, slots=True)
class ModelEvaluationMetrics:
    """Métricas de avaliação de um modelo preditivo binário calibrado.

    `brier_score` é a métrica principal de qualidade de calibração
    (quanto menor, melhor) — mais relevante aqui do que `accuracy`
    isoladamente, porque o output do modelo é consumido como uma
    probabilidade, não só como uma classe prevista.
    """

    accuracy: float
    brier_score: float
    roc_auc: float
    log_loss: float
    n_samples: int


class ModelNotFittedError(RuntimeError):
    """Levantado ao tentar prever/avaliar/guardar um modelo não treinado."""


class MatchOutcomeModel:
    """Modelo de previsão de vencedor de um jogo de ténis.

    Dois modos:
      - `"baseline"`: `LogisticRegression` simples, interpretável,
        usada para detetar regressões grosseiras entre versões.
      - `"production"`: `XGBClassifier` envolvido em
        `CalibratedClassifierCV` (calibração isotónica) — o modelo
        standard para dados tabulares estruturados, calibrado para que
        as probabilidades emitidas sejam estatisticamente fiáveis.
    """

    def __init__(self, model_type: ModelType = "production", *, random_state: int = 42) -> None:
        self._model_type = model_type
        self._random_state = random_state
        self._estimator = self._build_estimator()
        self._is_fitted = False

    def _build_estimator(self):
        if self._model_type == "baseline":
            return LogisticRegression(max_iter=1000)
        if self._model_type == "production":
            base_estimator = XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self._random_state,
                eval_metric="logloss",
            )
            # cv=3: com datasets de portfólio (milhares, não milhões de
            # jogos), 3 folds equilibra estabilidade da calibração com
            # ter dados suficientes por fold para treinar o XGBoost base.
            return CalibratedClassifierCV(base_estimator, method="isotonic", cv=3)
        raise ValueError(f"model_type deve ser 'baseline' ou 'production', recebeu {self._model_type!r}")

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        run_name: str | None = None,
        log_to_mlflow: bool = True,
    ) -> ModelEvaluationMetrics:
        """Treina o modelo e devolve as métricas de avaliação (in-sample).

        Regista parâmetros, métricas e o modelo treinado no MLflow
        (tracking local em ficheiro), permitindo comparar versões de
        forma reprodutível — conforme especificado na stack tecnológica.
        """
        if log_to_mlflow:
            mlflow.set_tracking_uri(_MLFLOW_TRACKING_URI)
            mlflow.set_experiment(_EXPERIMENT_NAME)
            with mlflow.start_run(run_name=run_name):
                metrics = self._fit_and_evaluate(X, y)
                mlflow.log_param("model_type", self._model_type)
                mlflow.log_param("n_features", X.shape[1])
                mlflow.log_metrics(
                    {
                        "accuracy": metrics.accuracy,
                        "brier_score": metrics.brier_score,
                        "roc_auc": metrics.roc_auc,
                        "log_loss": metrics.log_loss,
                    }
                )
                mlflow.sklearn.log_model(self._estimator, name="model")
            return metrics
        return self._fit_and_evaluate(X, y)

    def _fit_and_evaluate(self, X: np.ndarray, y: np.ndarray) -> ModelEvaluationMetrics:
        self._estimator.fit(X, y)
        self._is_fitted = True
        return self.evaluate(X, y)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Devolve `P(jogador1 vence)` para cada linha de `X`."""
        self._require_fitted()
        return self._estimator.predict_proba(X)[:, 1]

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> ModelEvaluationMetrics:
        """Calcula métricas de avaliação sobre `(X, y)`."""
        self._require_fitted()
        proba = self.predict_proba(X)
        predictions = (proba >= 0.5).astype(int)

        return ModelEvaluationMetrics(
            accuracy=float(accuracy_score(y, predictions)),
            brier_score=float(brier_score_loss(y, proba)),
            roc_auc=float(roc_auc_score(y, proba)),
            log_loss=float(log_loss(y, proba)),
            n_samples=len(y),
        )

    def save(self, path: str | Path) -> None:
        """Serializa o modelo treinado para disco via joblib."""
        self._require_fitted()
        joblib.dump({"estimator": self._estimator, "model_type": self._model_type}, path)

    @classmethod
    def load(cls, path: str | Path) -> MatchOutcomeModel:
        """Carrega um modelo previamente treinado e guardado com `save()`."""
        payload = joblib.load(path)
        instance = cls(model_type=payload["model_type"])
        instance._estimator = payload["estimator"]
        instance._is_fitted = True
        return instance

    def _require_fitted(self) -> None:
        if not self._is_fitted:
            raise ModelNotFittedError(
                "O modelo tem de ser treinado (fit) antes desta operação."
            )
