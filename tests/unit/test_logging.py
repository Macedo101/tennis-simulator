"""Testes de configuração de logging estruturado (`app.core.logging`)."""
from __future__ import annotations

import io
import json
import logging

from app.core.logging import configure_logging, get_logger


def test_configure_logging_json_mode_produces_valid_json_lines() -> None:
    configure_logging(json_logs=True, log_level="INFO")
    logger = get_logger("test.logger")

    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handler = root_logger.handlers[0]
    original_handler.stream = stream

    logger.info("test_event", foo="bar", count=3)

    output = stream.getvalue().strip()
    payload = json.loads(output)

    assert payload["event"] == "test_event"
    assert payload["foo"] == "bar"
    assert payload["count"] == 3
    assert payload["level"] == "info"
    assert "timestamp" in payload


def test_configure_logging_console_mode_does_not_raise() -> None:
    # Modo humano (desenvolvimento) — só confirma que não rebenta e que
    # o logger fica utilizável; o formato exato não é JSON, não faz
    # sentido fazer parsing estrito aqui.
    configure_logging(json_logs=False, log_level="DEBUG")
    logger = get_logger("test.console")

    logger.info("console_event", detail="ok")  # não deve levantar exceção


def test_get_logger_returns_bound_logger_supporting_bind() -> None:
    configure_logging(json_logs=True)
    logger = get_logger("test.bind")

    bound = logger.bind(request_id="abc-123")
    # `.bind()` devolve um novo logger com contexto adicional — não deve
    # levantar exceção nem alterar o logger original.
    assert bound is not None
