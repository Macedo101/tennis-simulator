"""Schemas de autenticação."""
from __future__ import annotations

import datetime
import re
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Mínimo 10 caracteres, 1 maiúscula, 1 número — conforme a
        especificação da API REST (secção `POST /auth/register`)."""
        if not re.search(r"[A-Z]", value):
            raise ValueError("A password deve conter pelo menos uma letra maiúscula.")
        if not re.search(r"\d", value):
            raise ValueError("A password deve conter pelo menos um número.")
        return value


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    created_at: datetime.datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
