"""
MergeMind — Database Setup

Configures SQLite via SQLAlchemy with session management.
Tables are created automatically on application startup.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

# ── Engine Setup ──────────────────────────────────────────────────────
# connect_args={"check_same_thread": False} is required for SQLite
# because SQLite only allows access from the thread that created it,
# but FastAPI may use multiple threads for request handling.
settings = get_settings()
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # Set to True for SQL query logging during debugging
)

# ── Session Factory ───────────────────────────────────────────────────
# Each request gets its own session via the get_db dependency
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Base Class ────────────────────────────────────────────────────────
# All ORM models inherit from this base
Base = declarative_base()


def init_db():
    """
    Create all database tables if they don't exist.
    Called once during application startup in main.py.
    """
    Base.metadata.create_all(bind=engine)


def get_db():
    """
    FastAPI dependency that provides a database session.
    
    Usage in route handlers:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    
    The session is automatically closed after the request completes,
    even if an exception occurs (thanks to the finally block).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
