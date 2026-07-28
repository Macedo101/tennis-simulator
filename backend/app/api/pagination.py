"""Paginação cursor-based (keyset), conforme a especificação da API REST.

Codifica o par `(created_at, id)` do último item de uma página em
base64 — o cliente devolve-o tal como recebeu, sem interpretar o seu
conteúdo. Preferida a `OFFSET` porque tem performance constante
independentemente da profundidade da página e é estável sob escrita
concorrente (ver justificação completa na especificação da API REST,
secção 3).
"""
from __future__ import annotations

import base64
import binascii
import datetime
import json
import uuid
from dataclasses import dataclass


class InvalidCursorError(ValueError):
    """Levantado quando um cursor fornecido pelo cliente é inválido."""


@dataclass(frozen=True, slots=True)
class Cursor:
    """Posição decodificada de um cursor de paginação."""

    created_at: datetime.datetime
    id: uuid.UUID


def encode_cursor(created_at: datetime.datetime, entity_id: uuid.UUID) -> str:
    """Codifica `(created_at, id)` num cursor opaco em base64."""
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": str(entity_id)}
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_cursor(cursor: str) -> Cursor:
    """Decodifica um cursor previamente gerado por `encode_cursor`.

    Levanta `InvalidCursorError` para qualquer cursor malformado — nunca
    deixa escapar `binascii.Error`/`json.JSONDecodeError`/`KeyError`
    crus para o chamador (router), que os traduziria de forma pouco
    clara num 500 em vez de um 422 informativo.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
        return Cursor(
            created_at=datetime.datetime.fromisoformat(payload["created_at"]),
            id=uuid.UUID(payload["id"]),
        )
    except (binascii.Error, ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"Cursor inválido: {cursor!r}") from exc
