"""Database service functions using SQLAlchemy Session."""
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, or_
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.schemas import Couple, Song
from app.utils.helpers import generate_unique_id, generate_song_key
from app.utils.logger import logger
from app.db.models import SongORM, FingerprintORM
from app.core.fingerprinting import ALGORITHM_VERSION

# Rows per INSERT / IN (...) statement; keeps statements well under Postgres' parameter limit
CHUNK_SIZE = 5000


def _insert_ignore_duplicates(db: Session, rows: List[dict]):
    """INSERT ... ON CONFLICT DO NOTHING for fingerprint rows (Postgres or SQLite)."""
    dialect = postgresql if db.get_bind().dialect.name == "postgresql" else sqlite
    db.execute(dialect.insert(FingerprintORM).values(rows).on_conflict_do_nothing())


def _chunks(items: list, size: int = CHUNK_SIZE):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def store_fingerprints(db: Session, fingerprints: Dict[int, Couple]) -> None:
    """Store fingerprints in the database."""
    if not fingerprints:
        return
    rows = [
        {
            "address": int(address),
            "anchorTimeMs": int(couple.anchor_time_ms),
            "songID": int(couple.song_id),
        }
        for address, couple in fingerprints.items()
    ]
    try:
        for chunk in _chunks(rows):
            _insert_ignore_duplicates(db, chunk)
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

    for chunk in _chunks([int(a) for a in addresses]):
        rows = db.query(
            FingerprintORM.address,
            FingerprintORM.anchorTimeMs,
            FingerprintORM.songID,
        ).filter(FingerprintORM.address.in_(chunk)).all()

        for address, anchor_time_ms, song_id in rows:
            couples.setdefault(int(address), []).append(
                Couple(anchor_time_ms=int(anchor_time_ms), song_id=int(song_id))
            )

    return couples


def total_songs(db: Session) -> int:
    """Get total number of songs."""
    return db.query(SongORM).count()


def register_song(db: Session, song_title: str, song_artist: str, yt_id: str) -> int:
    """Register a new song and return its ID."""
    song_key = generate_song_key(song_title, song_artist)

    if db.query(SongORM.id).filter(SongORM.key == song_key).first():
        raise ValueError(f"'{song_title}' by '{song_artist}' already exists")

    # Retry on the (very unlikely) chance of a random ID collision
    for _ in range(3):
        song_id = generate_unique_id()
        db.add(SongORM(
            id=song_id,
            title=song_title,
            artist=song_artist,
            ytID=yt_id,
            key=song_key,
            algorithm_version=ALGORITHM_VERSION,
        ))
        try:
            db.commit()
            return song_id
        except IntegrityError as exc:
            db.rollback()
            if db.query(SongORM.id).filter(SongORM.key == song_key).first():
                raise ValueError(f"'{song_title}' by '{song_artist}' already exists") from exc
        except Exception as exc:
            db.rollback()
            raise ValueError(f"Failed to register song: {exc}") from exc

    raise ValueError("Failed to register song: could not allocate a unique ID")


def _to_song(result: SongORM) -> Song:
    return Song(
        title=result.title,
        artist=result.artist,
        youtube_id=result.ytID or "",
    )


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

    return _to_song(result), True


def get_song_by_id(db: Session, song_id: int) -> Tuple[Optional[Song], bool]:
    """Get song by ID."""
    return _get_song(db, "id", int(song_id))


def get_songs_by_ids(db: Session, song_ids: List[int]) -> Dict[int, Song]:
    """Get several songs by ID in one query."""
    if not song_ids:
        return {}
    rows = db.query(SongORM).filter(SongORM.id.in_([int(i) for i in song_ids])).all()
    return {int(row.id): _to_song(row) for row in rows}


def get_song_by_ytid(db: Session, yt_id: str) -> Tuple[Optional[Song], bool]:
    """Get song by YouTube ID."""
    return _get_song(db, "ytID", yt_id)


def get_song_by_key(db: Session, key: str) -> Tuple[Optional[Song], bool]:
    """Get song by key."""
    return _get_song(db, "key", key)


def get_song_row(db: Session, song_id: int) -> Optional[SongORM]:
    """Get the raw song row (including its ID), or None."""
    return db.query(SongORM).filter(SongORM.id == int(song_id)).first()


def list_songs(db: Session, limit: int, offset: int, search: Optional[str] = None) -> Tuple[List[SongORM], int]:
    """Page through songs ordered by title, optionally filtered by title/artist. Returns (rows, total matching)."""
    query = db.query(SongORM)
    if search:
        # Treat % and _ in the search text literally
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.filter(or_(
            SongORM.title.ilike(pattern, escape="\\"),
            SongORM.artist.ilike(pattern, escape="\\"),
        ))
    total = query.count()
    rows = query.order_by(SongORM.title, SongORM.artist).offset(offset).limit(limit).all()
    return rows, total


def outdated_song_ids(db: Session) -> List[int]:
    """IDs of songs fingerprinted with an older algorithm version."""
    rows = db.query(SongORM.id).filter(SongORM.algorithm_version < ALGORITHM_VERSION).all()
    return [int(row.id) for row in rows]


def count_fingerprints(db: Session, song_id: Optional[int] = None) -> int:
    """Count fingerprints, for one song or for the whole database."""
    query = db.query(func.count()).select_from(FingerprintORM)
    if song_id is not None:
        query = query.filter(FingerprintORM.songID == int(song_id))
    return query.scalar() or 0


def update_song(db: Session, song_id: int, title: str, artist: str, yt_id: str) -> SongORM:
    """Update a song's details. Raises LookupError if missing, ValueError if title+artist is taken."""
    song = get_song_row(db, song_id)
    if song is None:
        raise LookupError(f"Song {song_id} not found")

    key = generate_song_key(title, artist)
    clash = db.query(SongORM.id).filter(SongORM.key == key, SongORM.id != song.id).first()
    if clash:
        raise ValueError(f"'{title}' by '{artist}' already exists")

    song.title, song.artist, song.ytID, song.key = title, artist, yt_id, key
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(f"'{title}' by '{artist}' already exists") from exc
    db.refresh(song)
    return song


def replace_fingerprints(db: Session, song_id: int, fingerprints: Dict[int, Couple]) -> None:
    """Swap a song's fingerprints for a freshly computed set in one transaction."""
    try:
        db.query(FingerprintORM).filter(FingerprintORM.songID == int(song_id)).delete()
        rows = [
            {"address": int(a), "anchorTimeMs": int(c.anchor_time_ms), "songID": int(song_id)}
            for a, c in fingerprints.items()
        ]
        for chunk in _chunks(rows):
            _insert_ignore_duplicates(db, chunk)
        db.query(SongORM).filter(SongORM.id == int(song_id)).update({"algorithm_version": ALGORITHM_VERSION})
        db.commit()
    except Exception:
        db.rollback()
        raise


def delete_song_by_id(db: Session, song_id: int) -> None:
    """Delete song by ID, along with its fingerprints."""
    db.query(FingerprintORM).filter(FingerprintORM.songID == int(song_id)).delete()
    db.query(SongORM).filter(SongORM.id == int(song_id)).delete()
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
