"""
Auth JSON schemas for login and registration.
"""

from __future__ import annotations
from pydantic import BaseModel, EmailStr

class UserRegisterRequest(BaseModel):
    """Payload for creating a new user."""
    email: EmailStr
    password: str

class UserLoginRequest(BaseModel):
    """Payload for logging in."""
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    """Response containing the session JWT/Token."""
    access_token: str
    token_type: str = "bearer"
