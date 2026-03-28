"""
In-memory auth store for the hackathon MVP.

Uses hashlib for basic passwords and UUIDs for session tokens.
Lost on restart.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from app.logging_utils import trace_calls

# In-memory stores
# email -> {"pwd_hash": str, "user_id": str}
_users: dict[str, dict[str, str]] = {}
# access_token -> user_id
_sessions: dict[str, str] = {}


def _hash_password(password: str) -> str:
    """Hashes a password with SHA-256 for basic MVP security."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


@trace_calls
def register_user(email: str, password: str) -> str:
    """
    Registers a new user and returns a session token.

    Args:
        email: User email.
        password: Plain text password.
        
    Returns:
        The access token.
        
    Raises:
        ValueError: If email is already taken.
    """
    email = email.lower()
    if email in _users:
        raise ValueError("Email already registered")

    user_id = str(uuid.uuid4())
    _users[email] = {
        "pwd_hash": _hash_password(password),
        "user_id": user_id
    }
    
    # Generate and save session token
    token = str(uuid.uuid4())
    _sessions[token] = user_id
    
    return token


@trace_calls
def authenticate_user(email: str, password: str) -> Optional[str]:
    """
    Authenticates a user and returns a session token.

    Args:
        email: User email.
        password: Plain text password.
        
    Returns:
        The access token if valid, else None.
    """
    email = email.lower()
    user_record = _users.get(email)
    
    if not user_record:
        return None
        
    if user_record["pwd_hash"] != _hash_password(password):
        return None
        
    # Generate a new session token upon successive logins
    token = str(uuid.uuid4())
    _sessions[token] = user_record["user_id"]
    
    return token

@trace_calls
def get_user_id_from_token(token: str) -> Optional[str]:
    """Retrieves user_id from session token."""
    return _sessions.get(token)
