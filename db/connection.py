"""
db/connection.py — SQLAlchemy engine and session factory.

Reads DATABASE_URL from .env (defaults to sqlite:///data/olive.db).
To move to Postgres on the Mac mini: set DATABASE_URL=postgresql://... in .env.
All queries written against SQLAlchemy work unchanged.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

_REPO_ROOT = Path(__file__).parent.parent
_DEFAULT_DB = f"sqlite:///{_REPO_ROOT / 'data' / 'olive.db'}"

DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_DB)

# WAL mode for SQLite gives better read/write concurrency; ignored by Postgres
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)
Session = sessionmaker(bind=engine)


def get_session():
    return Session()


def init_db():
    """Create all tables (idempotent)."""
    from db.schema import Base  # local import avoids circular at module load
    from sqlalchemy import text
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
    Base.metadata.create_all(engine)
