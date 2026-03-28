"""
Auth JSON schemas for login and registration.
"""

from pydantic import BaseModel

class UserRegisterRequest(BaseModel):
    """Payload for creating a new user."""
    email: str
    password: str

class UserLoginRequest(BaseModel):
    """Payload for logging in."""
    email: str
    password: str

class AuthResponse(BaseModel):
    """Response containing the session JWT/Token."""
    access_token: str
    token_type: str = "bearer"
