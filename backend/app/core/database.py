from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Import models so metadata is registered.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Milestone 2 was narrowed from general clinical observation extraction to
    # policy-driven evidence retrieval. Remove only that obsolete derived table;
    # original PDFs, page text, and requirement-linked candidates are preserved.
    if inspect(engine).has_table("observations"):
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE observations")
