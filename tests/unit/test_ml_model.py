"""Testes do `MatchOutcomeModel` (baseline e produção)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.ml.dataset import generate_synthetic_dataset
from app.ml.model import MatchOutcomeModel, ModelNotFittedError


@pytest.fixture(scope="module")
def synthetic_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    X_train, y_train = generate_synthetic_dataset(4_000, seed=1)
    X_test, y_test = generate_synthetic_dataset(1_000, seed=2)
    return X_train, y_train, X_test, y_test


def test_invalid_model_type_raises() -> None:
    with pytest.raises(ValueError, match="model_type"):
        MatchOutcomeModel(model_type="not-a-real-type")  # type: ignore[arg-type]


def test_operations_before_fit_raise_not_fitted_error(synthetic_data) -> None:
    X_train, _y_train, X_test, _y_test = synthetic_data
    model = MatchOutcomeModel(model_type="baseline")

    with pytest.raises(ModelNotFittedError):
        model.predict_proba(X_test)
    with pytest.raises(ModelNotFittedError):
        model.evaluate(X_test, np.zeros(len(X_test)))
    with pytest.raises(ModelNotFittedError):
        model.save("/tmp/should-not-be-created.joblib")


def test_baseline_model_recovers_known_signal(synthetic_data) -> None:
    X_train, y_train, X_test, y_test = synthetic_data
    model = MatchOutcomeModel(model_type="baseline")

    model.fit(X_train, y_train, log_to_mlflow=False)
    metrics = model.evaluate(X_test, y_test)

    # Dataset sintético com sinal forte -> baseline deve superar
    # claramente um classificador aleatório (accuracy ~0.5, AUC ~0.5).
    assert metrics.accuracy > 0.65
    assert metrics.roc_auc > 0.7
    assert 0.0 <= metrics.brier_score <= 0.25
    assert metrics.n_samples == len(y_test)


def test_production_model_recovers_known_signal(synthetic_data) -> None:
    X_train, y_train, X_test, y_test = synthetic_data
    model = MatchOutcomeModel(model_type="production")

    model.fit(X_train, y_train, log_to_mlflow=False)
    metrics = model.evaluate(X_test, y_test)

    assert metrics.accuracy > 0.65
    assert metrics.roc_auc > 0.7


def test_predict_proba_returns_values_in_unit_interval(synthetic_data) -> None:
    X_train, y_train, X_test, _y_test = synthetic_data
    model = MatchOutcomeModel(model_type="baseline")
    model.fit(X_train, y_train, log_to_mlflow=False)

    proba = model.predict_proba(X_test)

    assert proba.shape == (len(X_test),)
    assert (proba >= 0.0).all() and (proba <= 1.0).all()


def test_save_and_load_round_trip_preserves_predictions(synthetic_data) -> None:
    X_train, y_train, X_test, _y_test = synthetic_data
    model = MatchOutcomeModel(model_type="baseline")
    model.fit(X_train, y_train, log_to_mlflow=False)
    original_predictions = model.predict_proba(X_test)

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "model.joblib"
        model.save(path)
        assert path.exists()

        loaded_model = MatchOutcomeModel.load(path)
        loaded_predictions = loaded_model.predict_proba(X_test)

    np.testing.assert_array_almost_equal(original_predictions, loaded_predictions)


def test_fit_with_mlflow_logging_does_not_raise(synthetic_data) -> None:
    X_train, y_train, _X_test, _y_test = synthetic_data
    model = MatchOutcomeModel(model_type="baseline")

    # Não deve levantar exceção com o tracking MLflow ativo (ficheiro local).
    metrics = model.fit(X_train[:200], y_train[:200], run_name="test-run", log_to_mlflow=True)

    assert metrics.n_samples == 200
