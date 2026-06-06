import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_URL = os.getenv("RENT_RADAR_DB_URL", "sqlite:////data/rent_radar.sqlite")

engine = create_engine(
    DB_URL,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)


def get_session():
    return SessionLocal()