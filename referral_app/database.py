"""Database configuration and session helpers."""

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings

# Lazily create a SQLAlchemy engine that talks to PostgreSQL.  The same code will
# also work with SQLite (handy for local development) because SQLAlchemy hides
# the vendor specific details.
engine = create_engine(settings.database_url, future=True)

# The session factory is used across the application when a database session is
# required.  Using autoflush/autocommit disabled keeps transaction control in the
# service logic.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
