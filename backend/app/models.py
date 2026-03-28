"""
SQLAlchemy ORM Data Models mapping to crave.db
"""

from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime
from datetime import datetime
import uuid

from app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    pwd_hash = Column(String, nullable=False)

class Session(Base):
    __tablename__ = "sessions"
    access_token = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)

class Profile(Base):
    __tablename__ = "profiles"
    user_id = Column(String, primary_key=True)
    name = Column(String, nullable=False, default="Crave Chef")
    avatar = Column(String, nullable=False, default="https://api.dicebear.com/7.x/notionists/svg?seed=crave")
    vegan = Column(Boolean, default=False)
    gluten_free = Column(Boolean, default=False)
    nut_free = Column(Boolean, default=False)
    dairy_free = Column(Boolean, default=False)
    allergies = Column(JSON, default=list) # Generic string list

class ParsedRecipe(Base):
    __tablename__ = "parsed_recipes"
    session_id = Column(String, primary_key=True, default=generate_uuid)
    dry_run = Column(Boolean, default=False)
    schema_dump = Column(JSON, nullable=False)

class CookedHistory(Base):
    __tablename__ = "cooked_history"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, index=True, nullable=False)
    recipe_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    rating = Column(Integer, nullable=False)
    tags = Column(JSON, default=list)
    cooked_at = Column(DateTime, default=datetime.utcnow)

class SavedRecipe(Base):
    __tablename__ = "saved_recipes"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, index=True, nullable=False)
    recipe_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    saved_at = Column(DateTime, default=datetime.utcnow)
