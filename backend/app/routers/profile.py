"""
Profile REST endpoints, protected by session token.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from app.logging_utils import trace_calls
from app.schemas.profile import UserProfile, ProfileUpdateRequest
from app.services.profile_store import get_or_create_profile, update_profile
from app.services.auth_store import get_user_id_from_token

router = APIRouter(prefix="/api/profile", tags=["profile"])

async def get_current_user_id(authorization: str = Header(None)) -> str:
    """Dependency to extract user_id from the Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token",
        )
    
    token = authorization.split(" ")[1]
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid token",
        )
    return user_id


@router.get("", response_model=UserProfile)
@trace_calls
async def get_profile(user_id: str = Depends(get_current_user_id)) -> UserProfile:
    """Returns the authenticated user's profile state."""
    return get_or_create_profile(user_id)


@router.put("", response_model=UserProfile)
@trace_calls
async def update_user_profile(
    updates: ProfileUpdateRequest,
    user_id: str = Depends(get_current_user_id)
) -> UserProfile:
    """Updates the user's dietary preferences and allergies."""
    return update_profile(user_id, updates)
