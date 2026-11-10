from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True, future=True)


def create_schema(engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
