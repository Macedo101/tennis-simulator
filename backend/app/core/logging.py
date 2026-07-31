"""Configuração de logging estruturado (JSON), via `structlog`.

Logs em JSON são pesquisáveis e correlacionáveis com métricas — cada
entrada inclui sempre `request_id` (ver `app/core/request_context.py`),
o que permite reconstituir toda a atividade de um pedido específico
mesmo com múltiplos serviços/routers a escrever logs independentemente.
"""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, json_logs: bool = True, log_level: str = "INFO") -> None:
    """Configura `structlog` (e a `logging` nativa por baixo) uma única vez.

    Chamado no arranque da aplicação (`app/main.py`). `json_logs=False`
    é útil em desenvolvimento local (saída legível por humanos no
    terminal); `True` é o modo de produção (uma linha JSON por evento,
    consumível por Grafana Loki/qualquer agregador de logs).
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Silencia o access-log verboso do Uvicorn — o `RequestLoggingMiddleware`
    # (ver `app/core/request_logging.py`) já regista cada pedido de forma
    # estruturada, com request_id; o access-log nativo duplicaria a
    # informação num formato de texto livre, não-estruturado.
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Obtém um logger estruturado, tipicamente com `__name__` do módulo chamador."""
    return structlog.get_logger(name)
