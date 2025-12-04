"""Database service functions using SQLAlchemy Session."""
from typing import Dict, List, Optional, Tuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.schemas import Couple, Song
from app.utils.helpers import generate_unique_id, generate_song_key
from app.utils.logger import logger
from app.db.models import SongORM, FingerprintORM


def store_fingerprints(db: Session, fingerprints: Dict[int, Couple]) -> None:
    """Store fingerprints in the database."""
    if not fingerprints:
        return
    try:
        for address, couple in fingerprints.items():
            fp = FingerprintORM(
                address=int(address),
                anchorTimeMs=int(couple.anchor_time_ms),
                songID=int(couple.song_id),
            )
            db.merge(fp)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Error storing fingerprints: {exc}")
        raise


def get_couples(db: Session, addresses: List[int]) -> Dict[int, List[Couple]]:
    """Get couples for given addresses."""
    couples: Dict[int, List[Couple]] = {}
    if not addresses:
        return couples

    rows = db.query(
        FingerprintORM.address,
        FingerprintORM.anchorTimeMs,
        FingerprintORM.songID,
    ).filter(FingerprintORM.address.in_([int(a) for a in addresses])).all()

    for address, anchor_time_ms, song_id in rows:
        address_int = int(address)
        couples.setdefault(address_int, []).append(
            Couple(anchor_time_ms=int(anchor_time_ms), song_id=int(song_id))
        )

    return couples


def total_songs(db: Session) -> int:
    """Get total number of songs."""
    return db.query(SongORM).count()


def register_song(db: Session, song_title: str, song_artist: str, yt_id: str) -> int:
    """Register a new song and return its ID."""
    song_id = generate_unique_id()
    song_key = generate_song_key(song_title, song_artist)

    song = SongORM(
        id=int(song_id),
        title=song_title,
        artist=song_artist,
        ytID=yt_id,
        key=song_key,
    )
    try:
        db.add(song)
        db.commit()
        return int(song_id)
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(f"Song with ytID or key already exists: {exc}") from exc
    except Exception as exc:
        db.rollback()
        raise ValueError(f"Failed to register song: {exc}") from exc


def _get_song(db: Session, filter_key: str, value) -> Tuple[Optional[Song], bool]:
    """Internal helper to get song by filter key."""
    if filter_key == "id":
        result = db.query(SongORM).filter(SongORM.id == int(value)).first()
    elif filter_key == "ytID":
        result = db.query(SongORM).filter(SongORM.ytID == value).first()
    elif filter_key == "key":
        result = db.query(SongORM).filter(SongORM.key == value).first()
    else:
        raise ValueError("Invalid filter key")

    if result is None:
        return None, False

    return (
        Song(
            title=result.title,
            artist=result.artist,
            youtube_id=result.ytID or "",
        ),
        True,
    )


def get_song_by_id(db: Session, song_id: int) -> Tuple[Optional[Song], bool]:
    """Get song by ID."""
    return _get_song(db, "id", int(song_id))


def get_song_by_ytid(db: Session, yt_id: str) -> Tuple[Optional[Song], bool]:
    """Get song by YouTube ID."""
    return _get_song(db, "ytID", yt_id)


def get_song_by_key(db: Session, key: str) -> Tuple[Optional[Song], bool]:
    """Get song by key."""
    return _get_song(db, "key", key)


def delete_song_by_id(db: Session, song_id: int) -> None:
    """Delete song by ID."""
    song = db.query(SongORM).filter(SongORM.id == int(song_id)).first()
    if song:
        db.delete(song)
        db.commit()


def delete_collection(db: Session, collection_name: str) -> None:
    """Delete a collection/table."""
    if collection_name == "songs":
        db.query(SongORM).delete()
    elif collection_name == "fingerprints":
        db.query(FingerprintORM).delete()
    else:
        logger.warning(
            f"Ignoring delete_collection for unknown collection: {collection_name}"
        )
        return
    db.commit()

