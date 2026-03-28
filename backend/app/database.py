"""
Database configuration and session factory.
Uses SQLite for MVP.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Target crave.db flatfile relative to the backend/ execution folder
SQLALCHEMY_DATABASE_URL = "sqlite:///./crave.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
