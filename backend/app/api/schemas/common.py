"""Schemas comuns: envelope de paginação e erros RFC 7807."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Metadados de paginação cursor-based, devolvidos em todas as listagens."""

    next_cursor: str | None = Field(
        default=None,
        description="Cursor opaco para a página seguinte; `null` se não houver mais.",
    )
    has_more: bool = Field(description="Se existem mais resultados para além desta página.")
    limit: int = Field(description="Número máximo de itens pedido para esta página.")


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope comum a todas as respostas de listagem paginada."""

    data: list[T]
    pagination: PaginationMeta


class ProblemDetailError(BaseModel):
    """Um erro de validação individual, dentro de `ProblemDetail.errors`."""

    field: str
    message: str


class ProblemDetail(BaseModel):
    """Formato de erro uniforme (RFC 7807), conforme a especificação da API."""

    type: str = Field(description="URI identificando o tipo de erro.")
    title: str = Field(description="Resumo legível do tipo de erro.")
    status: int = Field(description="Código de estado HTTP.")
    detail: str = Field(description="Explicação específica deste erro em particular.")
    instance: str = Field(description="Path do pedido que originou o erro.")
    errors: list[ProblemDetailError] | None = Field(
        default=None, description="Detalhe por campo, quando aplicável (ex.: 422)."
    )
