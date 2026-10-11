from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from conf.settings import Settings

settings = Settings()

engine = create_engine(
    settings.database_url,
    connect_args={"connect_timeout": settings.db_connect_timeout},
    hide_parameters=True,
    max_overflow=5,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session]:
    """Provide a session and close it after each request, including failures."""
    with SessionLocal() as db:
        yield db
