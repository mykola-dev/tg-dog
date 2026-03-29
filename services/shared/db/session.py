from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.shared.config import load_config


def build_engine(echo: bool = False):
    config = load_config()
    return create_engine(config.database_url, echo=echo, future=True)


def build_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=build_engine(), autoflush=False, autocommit=False)
