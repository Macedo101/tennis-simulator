"""Testes do dependency `require_admin` (Módulo 7)."""
from __future__ import annotations

import uuid

import pytest

from app.api.deps import require_admin
from app.models.auth import User
from app.services.auth_service import InsufficientPermissionsError


def _make_user(role: str) -> User:
    return User(
        id=uuid.uuid4(),
        email="x@example.com",
        full_name="X",
        hashed_password="irrelevant",
        role=role,
    )


async def test_require_admin_allows_admin_user() -> None:
    admin = _make_user("admin")

    result = await require_admin(admin)

    assert result is admin


async def test_require_admin_rejects_regular_user() -> None:
    regular_user = _make_user("user")

    with pytest.raises(InsufficientPermissionsError):
        await require_admin(regular_user)
