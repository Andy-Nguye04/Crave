"""
Auth REST endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from app.logging_utils import trace_calls
from app.schemas.auth import UserLoginRequest, UserRegisterRequest, AuthResponse
from app.services.auth_store import authenticate_user, register_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
@trace_calls
async def register(request: UserRegisterRequest) -> AuthResponse:
    """Register a new user and return a session token."""
    try:
        token = register_user(request.email, request.password)
        return AuthResponse(access_token=token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=AuthResponse)
@trace_calls
async def login(request: UserLoginRequest) -> AuthResponse:
    """Authenticate returning a session token."""
    token = authenticate_user(request.email, request.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return AuthResponse(access_token=token)
