"""Router de autenticação (`/api/v1/auth`)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import AuthServiceDep, CurrentUser
from app.api.schemas.auth import (
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, auth_service: AuthServiceDep) -> UserResponse:
    user = await auth_service.register(
        email=payload.email, password=payload.password, full_name=payload.full_name
    )
    return UserResponse.model_validate(user, from_attributes=True)


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: AuthServiceDep,
) -> TokenResponse:
    """Login via OAuth2 Password Flow (`application/x-www-form-urlencoded`).

    O standard OAuth2 exige o campo `username` mesmo quando o
    identificador real é um email — `form_data.username` é tratado
    como o email do utilizador, conforme a especificação da API REST.
    """
    tokens = await auth_service.login(email=form_data.username, password=form_data.password)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, auth_service: AuthServiceDep) -> TokenResponse:
    tokens = await auth_service.refresh(payload.refresh_token)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, auth_service: AuthServiceDep) -> None:
    await auth_service.logout(payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user, from_attributes=True)
