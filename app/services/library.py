"""
Song library management: adding, editing, removing and re-indexing songs.

These are only exposed through the command line (app/cli.py), never over HTTP.
Errors are raised as ValueError (bad input / conflict) or LookupError (not found).
"""
import os
import shutil
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.config import KEEP_AUDIO, SONGS_DIR, TMP_DIR
from app.db.models import SongORM
from app.models.schemas import Track
from app.services.audio import fingerprint_audio, get_metadata
from app.services.db_service import (
    count_fingerprints, delete_collection, delete_song_by_id, get_song_row,
    outdated_song_ids, replace_fingerprints, total_songs, update_song,
)
from app.services.spotify_downloader import dl_album, dl_playlist, dl_single_track, process_and_save_song
from app.services.youtube import get_youtube_id
from app.utils.helpers import create_folder, delete_file, move_file, song_file_path

AUDIO_EXTENSIONS = (".wav", ".m4a")


def download_from_spotify(spotify_url: str) -> int:
    """Download and fingerprint a Spotify track, album or playlist. Returns how many songs were added."""
    if "album" in spotify_url:
        return dl_album(spotify_url, SONGS_DIR)
    if "playlist" in spotify_url:
        return dl_playlist(spotify_url, SONGS_DIR)
    if "track" in spotify_url:
        return dl_single_track(spotify_url, SONGS_DIR)
    raise ValueError("Not a Spotify track, album or playlist URL")


def add_file(db: Session, path: str, title: Optional[str] = None, artist: Optional[str] = None, force: bool = False) -> SongORM:
    """
    Fingerprint a local audio file and add it to the library.
    Title and artist are read from the file's tags unless given. The original file is never modified.
    """
    if not os.path.isfile(path):
        raise ValueError(f"File not found: {path}")

    try:
        metadata = get_metadata(path)
    except RuntimeError:
        raise ValueError(f"Could not read audio file: {path}")

    tags = metadata.get("format", {}).get("tags", {})
    try:
        duration = float(metadata.get("format", {}).get("duration", "0"))
    except ValueError:
        duration = 0.0

    track_title = (title or tags.get("title") or os.path.splitext(os.path.basename(path))[0]).strip()
    track_artist = (artist or tags.get("artist") or "").strip()
    if not track_title or not track_artist:
        raise ValueError("Title and artist are required (none found in the file's tags); pass --title/--artist")

    track = Track(title=track_title, artist=track_artist, album=tags.get("album", ""), duration=round(duration))
    yt_id = get_youtube_id(track)
    if not yt_id and not force:
        raise ValueError("Could not find the song on YouTube (use --force to add it anyway)")

    # Work on a copy: converting to WAV deletes the input file
    create_folder(TMP_DIR)
    work_path = os.path.join(TMP_DIR, uuid.uuid4().hex + os.path.splitext(path)[1].lower())
    shutil.copyfile(path, work_path)
    wav_path = os.path.splitext(work_path)[0] + ".wav"
    try:
        song_id = process_and_save_song(work_path, track_title, track_artist, yt_id or "", db)
        if KEEP_AUDIO and os.path.exists(wav_path):
            create_folder(SONGS_DIR)
            move_file(wav_path, song_file_path(track_title, track_artist))
    finally:
        delete_file(work_path)
        delete_file(wav_path)

    return get_song_row(db, song_id)


def get_song_or_raise(db: Session, song_id: int) -> SongORM:
    song = get_song_row(db, song_id)
    if song is None:
        raise LookupError(f"Song {song_id} not found")
    return song


def edit_song(db: Session, song_id: int, title: Optional[str] = None, artist: Optional[str] = None,
              youtube_id: Optional[str] = None) -> SongORM:
    """Change a song's title, artist or YouTube ID. Its audio file is renamed to match."""
    song = get_song_or_raise(db, song_id)
    old_path = song_file_path(song.title, song.artist)

    title = (title if title is not None else song.title).strip()
    artist = (artist if artist is not None else song.artist).strip()
    yt_id = (youtube_id if youtube_id is not None else song.ytID or "").strip()
    if not title or not artist:
        raise ValueError("Title and artist can't be empty")

    song = update_song(db, song_id, title, artist, yt_id)

    new_path = song_file_path(title, artist)
    if new_path != old_path and os.path.exists(old_path):
        move_file(old_path, new_path)
    return song


def erase_song(db: Session, song_id: int, include_files: bool = False) -> SongORM:
    """Erase one song and its fingerprints. include_files also deletes its audio file."""
    song = get_song_or_raise(db, song_id)
    path = song_file_path(song.title, song.artist)
    delete_song_by_id(db, song_id)
    if include_files:
        delete_file(path)
    return song


def erase_all(db: Session, include_files: bool = False) -> None:
    """Erase every song and fingerprint. include_files also deletes all audio files."""
    delete_collection(db, "fingerprints")
    delete_collection(db, "songs")

    if include_files and os.path.isdir(SONGS_DIR):
        for file in os.listdir(SONGS_DIR):
            file_path = os.path.join(SONGS_DIR, file)
            if os.path.isfile(file_path) and os.path.splitext(file)[1] in AUDIO_EXTENSIONS:
                os.remove(file_path)


def reindex_song(db: Session, song_id: int) -> int:
    """Recompute a song's fingerprints from its audio file. Returns the new fingerprint count."""
    song = get_song_or_raise(db, song_id)
    path = song_file_path(song.title, song.artist)
    if not os.path.exists(path):
        raise ValueError(f"No audio file for '{song.title}' by '{song.artist}' ({path}); re-add the song instead")

    replace_fingerprints(db, song.id, fingerprint_audio(path, song.id))
    return count_fingerprints(db, song.id)


def stats(db: Session) -> dict:
    """Library size: songs, fingerprints, and the audio files kept on disk."""
    files = []
    if os.path.isdir(SONGS_DIR):
        files = [
            os.path.join(SONGS_DIR, f) for f in os.listdir(SONGS_DIR)
            if os.path.splitext(f)[1] in AUDIO_EXTENSIONS
        ]
    return {
        "songs": total_songs(db),
        "outdated_songs": len(outdated_song_ids(db)),
        "fingerprints": count_fingerprints(db),
        "audio_files": len(files),
        "audio_bytes": sum(os.path.getsize(f) for f in files if os.path.isfile(f)),
        "songs_dir": os.path.abspath(SONGS_DIR),
    }
