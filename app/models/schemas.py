"""Pydantic models for data structures."""
from typing import Optional
from pydantic import BaseModel, Field

from app.config import MAX_UPLOAD_BYTES


class Couple(BaseModel):
    """Represents a fingerprint couple with anchor time and song ID."""
    anchor_time_ms: int
    song_id: int


class RecordData(BaseModel):
    """Audio recording data from client."""
    audio: str = Field(max_length=MAX_UPLOAD_BYTES * 4 // 3 + 4)  # Base64 encoded 16-bit PCM
    duration: float
    channels: int
    sample_rate: int
    sample_size: int


class Match(BaseModel):
    """Song match result."""
    song_id: int
    song_title: str
    song_artist: str
    youtube_id: str
    timestamp: int
    score: float


class Song(BaseModel):
    """Song information."""
    title: str
    artist: str
    youtube_id: str


class SongInfo(BaseModel):
    """A song in the library, as returned by the songs endpoints."""
    id: int
    title: str
    artist: str
    youtube_id: str
    youtube_url: Optional[str] = None


class SongDetail(SongInfo):
    """A song plus its fingerprint statistics."""
    fingerprint_count: int


class SongPage(BaseModel):
    """One page of the song list."""
    items: list[SongInfo]
    total: int
    limit: int
    offset: int


class Track(BaseModel):
    """Spotify track information."""
    title: str
    artist: str
    album: str
    artists: list[str] = []
    duration: int  # Duration in seconds


class FindRequest(BaseModel):
    """Request to find matches for a fingerprint computed by the client."""
    fingerprint: dict[int, int]  # Map of address -> anchor_time_ms

