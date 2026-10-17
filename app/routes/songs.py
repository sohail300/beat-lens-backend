"""Public, read-only song library endpoints."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.models import SongORM
from app.db.session import db_dependency
from app.models.schemas import SongDetail, SongInfo, SongPage
from app.services.db_service import count_fingerprints, get_song_row, list_songs, total_songs

router = APIRouter(prefix="/songs", tags=["songs"])


def to_song_info(song: SongORM) -> SongInfo:
    return SongInfo(
        id=song.id,
        title=song.title,
        artist=song.artist,
        youtube_id=song.ytID or "",
        youtube_url=f"https://www.youtube.com/watch?v={song.ytID}" if song.ytID else None,
    )


def to_song_detail(db, song: SongORM) -> SongDetail:
    return SongDetail(
        **to_song_info(song).model_dump(),
        fingerprint_count=count_fingerprints(db, song.id),
    )


@router.get("", response_model=SongPage)
def get_songs(
    db: db_dependency,
    search: Optional[str] = Query(None, description="Case-insensitive match on title or artist"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List songs in the library, alphabetically, with optional search and pagination."""
    rows, total = list_songs(db, limit, offset, search)
    return SongPage(items=[to_song_info(row) for row in rows], total=total, limit=limit, offset=offset)


@router.get("/total")
def get_total_songs(db: db_dependency):
    """Get total number of songs in database."""
    return {"total": total_songs(db)}


@router.get("/{song_id}", response_model=SongDetail)
def get_song(song_id: int, db: db_dependency):
    """Get one song, including how many fingerprints it has."""
    song = get_song_row(db, song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return to_song_detail(db, song)
