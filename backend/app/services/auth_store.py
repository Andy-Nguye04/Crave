"""
Auth store for the MVP.
Uses hashlib for basic passwords and UUIDs for session tokens.
Uses SQLite via SQLAlchemy.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from app.logging_utils import trace_calls
from app.database import SessionLocal
from app.models import User, Session

DEMO_USER_EMAIL = "demo@crave.app"
DEMO_USER_PASSWORD = "demo"
DEMO_TOKEN = "crave-demo-token-hackathon"


def _hash_password(password: str) -> str:
    """Hashes a password with SHA-256 for basic MVP security."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def ensure_demo_user() -> None:
    """Create the default demo user and session token if they don't exist."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == DEMO_USER_EMAIL).first()
        if not user:
            user = User(
                email=DEMO_USER_EMAIL,
                pwd_hash=_hash_password(DEMO_USER_PASSWORD),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        existing_session = db.query(Session).filter(
            Session.access_token == DEMO_TOKEN
        ).first()
        if not existing_session:
            db.add(Session(access_token=DEMO_TOKEN, user_id=user.id))
            db.commit()

@trace_calls
def register_user(email: str, password: str) -> str:
    email = email.lower()
    
    with SessionLocal() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise ValueError("Email already registered")

        user = User(
            email=email,
            pwd_hash=_hash_password(password)
        )
        db.add(user)
        db.commit()
        db.refresh(user) 
        
        token = str(uuid.uuid4())
        session_record = Session(access_token=token, user_id=user.id)
        db.add(session_record)
        db.commit()
    
    return token

@trace_calls
def authenticate_user(email: str, password: str) -> Optional[str]:
    email = email.lower()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            return None
            
        if user.pwd_hash != _hash_password(password):
            return None
            
        token = str(uuid.uuid4())
        session_record = Session(access_token=token, user_id=user.id)
        db.add(session_record)
        db.commit()
        
    return token

@trace_calls
def get_user_id_from_token(token: str) -> Optional[str]:
    with SessionLocal() as db:
        session_record = db.query(Session).filter(Session.access_token == token).first()
        if session_record:
            return session_record.user_id
    return None
