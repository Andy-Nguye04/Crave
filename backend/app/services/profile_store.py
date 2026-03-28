"""
In-memory profile store for the hackathon MVP.
Generates a default profile lazily on first GET.
"""

from typing import Optional
from app.logging_utils import trace_calls
from app.schemas.profile import UserProfile, ProfileUpdateRequest

# Map of user_id -> UserProfile
_profiles: dict[str, UserProfile] = {}

@trace_calls
def get_or_create_profile(user_id: str) -> UserProfile:
    """
    Fetches the profile for a user, or creates the generic "Crave Chef" 
    default profile if it doesn't exist yet.
    """
    if user_id not in _profiles:
        # Defaults defined in the schema
        _profiles[user_id] = UserProfile()
    return _profiles[user_id]

@trace_calls
def update_profile(user_id: str, updates: ProfileUpdateRequest) -> UserProfile:
    """
    Updates a user's dietary preferences and allergies.
    """
    profile = get_or_create_profile(user_id)
    profile.dietary_preferences = updates.dietary_preferences
    profile.other_allergies = updates.other_allergies
    return profile
