from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.shared.config import load_config


def build_engine(echo: bool = False):
    config = load_config()
    return create_engine(config.database_url, echo=echo, future=True)


_factory: sessionmaker | None = None


def get_session_factory() -> sessionmaker:
    global _factory
    if _factory is None:
        _factory = sessionmaker(bind=build_engine(), autoflush=False, autocommit=False)
    return _factory


def get_db():
    """FastAPI dependency: yields a DB session."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
