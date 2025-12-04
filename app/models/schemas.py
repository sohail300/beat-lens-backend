"""Pydantic models for data structures."""
from typing import Optional
from pydantic import BaseModel


class Couple(BaseModel):
    """Represents a fingerprint couple with anchor time and song ID."""
    anchor_time_ms: int
    song_id: int


class RecordData(BaseModel):
    """Audio recording data from client."""
    audio: str  # Base64 encoded audio
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


class Track(BaseModel):
    """Spotify track information."""
    title: str
    artist: str
    album: str
    artists: list[str] = []
    duration: int  # Duration in seconds


class DownloadRequest(BaseModel):
    """Request to download from Spotify."""
    spotify_url: str


class FindRequest(BaseModel):
    """Request to find matches for audio."""
    file_path: Optional[str] = None
    fingerprint: Optional[dict[int, int]] = None  # Map of address -> anchor_time_ms


class SaveRequest(BaseModel):
    """Request to save a song."""
    file_path: str
    force: bool = False


class EraseRequest(BaseModel):
    """Request to erase database/files."""
    db_only: bool = True
    all: bool = False


class DownloadStatus(BaseModel):
    """Download status message."""
    type: str  # "info", "success", "error"
    message: str

