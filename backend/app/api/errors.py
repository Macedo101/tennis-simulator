"""Tradução de exceções de domínio para respostas RFC 7807.

Registado uma única vez em `app/main.py` — os routers nunca fazem
`try/except` para converter erros em respostas HTTP; limitam-se a
deixar a exceção de domínio propagar, e é aqui que ela vira JSON.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.pagination import InvalidCursorError
from app.api.schemas.common import ProblemDetail
from app.cache.exceptions import RateLimitExceededError
from app.ml.model import ModelNotFittedError
from app.repositories.exceptions import DuplicateEntityError, EntityNotFoundError
from app.services.auth_service import InsufficientPermissionsError, InvalidCredentialsError


def _problem_response(
    request: Request, *, status_code: int, title: str, detail: str, type_suffix: str
) -> JSONResponse:
    problem = ProblemDetail(
        type=f"https://api.simulador-tenis.com/errors/{type_suffix}",
        title=title,
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
    )
    return JSONResponse(status_code=status_code, content=problem.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """Regista todos os exception handlers globais na app FastAPI."""

    @app.exception_handler(EntityNotFoundError)
    async def _handle_not_found(request: Request, exc: EntityNotFoundError) -> JSONResponse:
        return _problem_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            title="Recurso não encontrado",
            detail=str(exc),
            type_suffix="not-found",
        )

    @app.exception_handler(DuplicateEntityError)
    async def _handle_duplicate(request: Request, exc: DuplicateEntityError) -> JSONResponse:
        return _problem_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            title="Conflito de unicidade",
            detail=str(exc),
            type_suffix="conflict",
        )

    @app.exception_handler(InvalidCursorError)
    async def _handle_invalid_cursor(request: Request, exc: InvalidCursorError) -> JSONResponse:
        return _problem_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Erro de validação",
            detail=str(exc),
            type_suffix="validation-error",
        )

    @app.exception_handler(ValueError)
    async def _handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        return _problem_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Erro de validação",
            detail=str(exc),
            type_suffix="validation-error",
        )

    @app.exception_handler(InvalidCredentialsError)
    async def _handle_invalid_credentials(
        request: Request, exc: InvalidCredentialsError
    ) -> JSONResponse:
        response = _problem_response(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            title="Não autenticado",
            detail=str(exc),
            type_suffix="unauthorized",
        )
        # Cabeçalho exigido pelo standard OAuth2/Bearer para respostas 401.
        response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.exception_handler(InsufficientPermissionsError)
    async def _handle_insufficient_permissions(
        request: Request, exc: InsufficientPermissionsError
    ) -> JSONResponse:
        return _problem_response(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            title="Sem permissão",
            detail=str(exc),
            type_suffix="forbidden",
        )

    @app.exception_handler(ModelNotFittedError)
    async def _handle_model_not_fitted(
        request: Request, exc: ModelNotFittedError
    ) -> JSONResponse:
        return _problem_response(
            request,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            title="Modelo preditivo indisponível",
            detail=(
                "Ainda não existe um modelo preditivo treinado disponível para "
                "servir previsões."
            ),
            type_suffix="model-unavailable",
        )

    @app.exception_handler(RateLimitExceededError)
    async def _handle_rate_limit_exceeded(
        request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        response = _problem_response(
            request,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            title="Limite de pedidos excedido",
            detail=str(exc),
            type_suffix="rate-limit-exceeded",
        )
        response.headers["X-RateLimit-Limit"] = str(exc.limit)
        response.headers["X-RateLimit-Remaining"] = "0"
        response.headers["X-RateLimit-Reset"] = str(exc.reset_at)
        response.headers["Retry-After"] = str(exc.window_seconds)
        return response
