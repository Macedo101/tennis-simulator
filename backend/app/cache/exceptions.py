"""Exceções relacionadas com rate limiting."""
from __future__ import annotations


class RateLimitExceededError(Exception):
    """Levantada quando um limite de taxa (geral ou específico) é excedido."""

    def __init__(self, *, limit: int, window_seconds: int, reset_at: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.reset_at = reset_at
        super().__init__(
            f"Limite de {limit} pedidos por {window_seconds}s excedido."
        )
