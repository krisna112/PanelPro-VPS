"""SQLAlchemy engine, session factory and initialisation helpers."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from panelpro.config import CFG

engine = create_engine(
    f"sqlite:///{CFG.db_path}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create every table if it does not exist yet."""
    from panelpro.models.tables import Base  # local import avoids cycles

    CFG.ensure_dirs()
    Base.metadata.create_all(engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
