"""Middleware de logging estruturado por pedido.

Gera um `request_id` novo por pedido HTTP e liga-o ao contexto do
`structlog` (via `contextvars`) — qualquer `logger.info(...)` chamado
durante o processamento deste pedido, em qualquer router/serviço/
repositório, inclui automaticamente esse `request_id`, sem o passar
explicitamente por cada função.
"""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Liga um `request_id` ao contexto de logging e regista início/fim do pedido."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )

        logger.info("request_started")

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error("request_failed", duration_ms=duration_ms, exc_info=True)
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.info(
            "request_finished",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response
