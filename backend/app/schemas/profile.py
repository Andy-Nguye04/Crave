"""
Profile JSON schemas for user details and dietary preferences.
"""

from pydantic import BaseModel, Field

class DietaryPreferences(BaseModel):
    """Boolean toggles for common restrictions."""
    vegan: bool = False
    gluten_free: bool = False
    nut_free: bool = False
    dairy_free: bool = False

class UserProfile(BaseModel):
    """Full user profile including identity and dietary info."""
    name: str = "Crave Chef"
    avatar_url: str = "https://ui-avatars.com/api/?name=Crave+Chef&background=0f5238&color=fff&rounded=true"
    dietary_preferences: DietaryPreferences = Field(default_factory=DietaryPreferences)
    other_allergies: list[str] = Field(default_factory=list)

class ProfileUpdateRequest(BaseModel):
    """Payload for updating profile settings."""
    dietary_preferences: DietaryPreferences
    other_allergies: list[str]
