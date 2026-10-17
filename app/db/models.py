"""SQLAlchemy ORM models for the database schema."""
from sqlalchemy import BigInteger, Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SongORM(Base):
    """ORM model for the songs table."""

    __tablename__ = "songs"

    id = Column(BigInteger, primary_key=True)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    ytID = Column(String, nullable=True)
    key = Column(String, nullable=False, unique=True)
    # Fingerprint algorithm the song was indexed with (see app.core.fingerprinting.ALGORITHM_VERSION)
    algorithm_version = Column(Integer, nullable=False, server_default="1")


class FingerprintORM(Base):
    """ORM model for the fingerprints table."""

    __tablename__ = "fingerprints"

    address = Column(BigInteger, primary_key=True)
    anchorTimeMs = Column(BigInteger, primary_key=True)
    songID = Column(BigInteger, primary_key=True, index=True)


