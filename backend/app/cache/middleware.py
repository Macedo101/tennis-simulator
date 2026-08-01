"""Middleware de rate limiting geral (100/min autenticado, 20/min anónimo).

Aplicado a todos os pedidos (exceto os caminhos isentos abaixo) — os
headers `X-RateLimit-*` têm de aparecer "em todas as respostas"
conforme a especificação da API, o que só um middleware garante de
forma consistente (um `Depends()` por rota teria de ser repetido em
cada router e seria fácil de esquecer numa rota nova).
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api.schemas.common import ProblemDetail
from app.cache.rate_limiter import RateLimiter
from app.core.config import Settings, get_settings
from app.core.security import InvalidTokenError, decode_access_token

#: Caminhos isentos de rate limiting — documentação e health check não
#: são chamadas de negócio e não devem contar para o limite de ninguém.
_EXEMPT_PATH_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/health", "/metrics")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Aplica rate limiting geral e anota `X-RateLimit-*` em cada resposta."""

    def __init__(self, app: object, rate_limiter: RateLimiter) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._rate_limiter = rate_limiter

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if any(request.url.path.startswith(p) for p in _EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        settings = get_settings()
        key, limit = self._resolve_identity_and_limit(request, settings)

        result = await self._rate_limiter.check(key, limit=limit, window_seconds=60)

        if not result.allowed:
            problem = ProblemDetail(
                type="https://api.simulador-tenis.com/errors/rate-limit-exceeded",
                title="Limite de pedidos excedido",
                status=429,
                detail=f"Limite de {limit} pedidos por minuto excedido.",
                instance=str(request.url.path),
            )
            return JSONResponse(
                status_code=429,
                content=problem.model_dump(),
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(result.reset_at),
                    "Retry-After": str(max(1, result.reset_at - int(time.time()))),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_at)
        return response

    @staticmethod
    def _resolve_identity_and_limit(request: Request, settings: Settings) -> tuple[str, int]:
        """Decide a chave de rate limit (por utilizador ou por IP) e o limite aplicável."""
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[len("bearer ") :]
            try:
                payload = decode_access_token(token)
                return f"user:{payload['sub']}", settings.rate_limit_authenticated_per_minute
            except InvalidTokenError:
                pass  # token inválido -> tratado como anónimo (limite mais baixo)

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}", settings.rate_limit_unauthenticated_per_minute
