"""
Persistent profile store for the MVP.
Generates a default profile lazily on first GET.
"""

from typing import Optional
from app.logging_utils import trace_calls
from app.schemas.profile import UserProfile, ProfileUpdateRequest, DietaryPreferences
from app.models import Profile as ProfileModel
from app.database import SessionLocal

@trace_calls
def get_or_create_profile(user_id: str) -> UserProfile:
    with SessionLocal() as db:
        pro = db.query(ProfileModel).filter(ProfileModel.user_id == user_id).first()
        if not pro:
            pro = ProfileModel(user_id=user_id)
            db.add(pro)
            db.commit()
            db.refresh(pro)
            
        return UserProfile(
            name=pro.name,
            avatar_url=pro.avatar,
            dietary_preferences=DietaryPreferences(
                vegan=pro.vegan,
                gluten_free=pro.gluten_free,
                nut_free=pro.nut_free,
                dairy_free=pro.dairy_free,
            ),
            other_allergies=pro.allergies or []
        )

@trace_calls
def update_profile(user_id: str, updates: ProfileUpdateRequest) -> UserProfile:
    with SessionLocal() as db:
        pro = db.query(ProfileModel).filter(ProfileModel.user_id == user_id).first()
        if not pro:
            pro = ProfileModel(user_id=user_id)
            db.add(pro)
            
        if updates.dietary_preferences is not None:
            pro.vegan = updates.dietary_preferences.vegan
            pro.gluten_free = updates.dietary_preferences.gluten_free
            pro.nut_free = updates.dietary_preferences.nut_free
            pro.dairy_free = updates.dietary_preferences.dairy_free
            
        pro.allergies = updates.other_allergies
        db.commit()

    return get_or_create_profile(user_id)
