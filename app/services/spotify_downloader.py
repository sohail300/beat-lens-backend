"""Spotify download service."""
import os
import subprocess
import threading
import time
import concurrent.futures
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.schemas import Track
from app.services.spotify import track_info, playlist_info, album_info, song_key_exists, yt_id_exists
from app.services.youtube import get_youtube_id, download_yt_audio
from app.services.audio import fingerprint_audio
from app.db.session import SessionLocal
from app.services.db_service import (
    register_song, store_fingerprints, delete_song_by_id
)
from app.utils.helpers import correct_filename, generate_song_key, create_folder, delete_file
from app.utils.logger import logger
from app.config import KEEP_AUDIO


# Each worker runs yt-dlp, ffmpeg and fingerprinting; more than a few at once
# mostly just gets rate-limited by YouTube.
MAX_DOWNLOAD_WORKERS = min(4, os.cpu_count() or 1)


def add_tags(file_path: str, track: Track) -> None:
    """Add metadata tags to WAV file using FFmpeg."""
    temp_file = os.path.splitext(file_path)[0] + "_tagged.wav"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", file_path,
        "-c", "copy",
        "-metadata", f"album_artist={track.artist}",
        "-metadata", f"title={track.title}",
        "-metadata", f"artist={track.artist}",
        "-metadata", f"album={track.album}",
        temp_file
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        delete_file(temp_file)
        raise RuntimeError(f"Failed to add tags: {result.stderr[-500:]}")

    os.replace(temp_file, file_path)


def process_and_save_song(song_file_path: str, song_title: str, song_artist: str, yt_id: str, db: Optional[Session] = None) -> int:
    """Fingerprint a song file and save it to the database. Returns the new song ID."""
    should_close = db is None
    if db is None:
        db = SessionLocal()

    song_id = None
    try:
        song_id = register_song(db, song_title, song_artist, yt_id)
        fingerprints = fingerprint_audio(song_file_path, song_id)
        store_fingerprints(db, fingerprints)
        logger.info(f"Fingerprint for {song_title} by {song_artist} saved in DB successfully")
        return song_id
    except Exception:
        if song_id is not None:
            try:
                delete_song_by_id(db, song_id)
            except Exception as cleanup_exc:
                logger.error(f"Failed to clean up song {song_id}: {cleanup_exc}")
        raise
    finally:
        if should_close:
            db.close()


def get_yt_id(track: Track, db: Optional[Session] = None) -> str:
    """Get YouTube ID for track, refusing one that is already in the database."""
    yt_id = get_youtube_id(track)
    if not yt_id:
        raise ValueError(f"Could not get YouTube ID for {track.title} by {track.artist}")

    if yt_id_exists(yt_id, db):
        raise ValueError(f"YouTube ID ({yt_id}) already belongs to another song")

    return yt_id


def dl_track(tracks: List[Track], path: str) -> int:
    """Download tracks from YouTube and fingerprint them. Returns how many succeeded."""
    create_folder(path)
    total_tracks = 0
    lock = threading.Lock()

    def process_track(track: Track):
        nonlocal total_tracks
        # Create a new session for each track (thread-safe)
        db = SessionLocal()
        try:
            # Check if song exists
            title, artist = correct_filename(track.title, track.artist)
            if song_key_exists(generate_song_key(title, artist), db):
                logger.info(f"'{track.title}' by '{track.artist}' already exists.")
                return

            yt_id = get_yt_id(track, db)

            file_path = os.path.join(path, f"{title} - {artist}")

            # Download from YouTube
            video_url = f"https://www.youtube.com/watch?v={yt_id}"
            wav_file_path = download_yt_audio(video_url, file_path)

            process_and_save_song(wav_file_path, title, artist, yt_id, db)

            if not KEEP_AUDIO:
                delete_file(wav_file_path)
            elif os.path.exists(wav_file_path):
                add_tags(wav_file_path, track)

            logger.info(f"'{track.title}' by '{track.artist}' was downloaded")
            with lock:
                total_tracks += 1
        except Exception as e:
            logger.error(f"Error processing track {track.title}: {e}")
        finally:
            db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
        list(executor.map(process_track, tracks))

    logger.info(f"Total tracks downloaded: {total_tracks}")
    return total_tracks


def dl_single_track(url: str, save_path: str) -> int:
    """Download a single track from Spotify."""
    logger.info(f"Getting track info: {url}")
    track = track_info(url)

    logger.info("Now downloading track")
    return dl_track([track], save_path)


def dl_playlist(url: str, save_path: str) -> int:
    """Download playlist from Spotify."""
    tracks = playlist_info(url)
    time.sleep(1)
    logger.info("Now downloading playlist")
    return dl_track(tracks, save_path)


def dl_album(url: str, save_path: str) -> int:
    """Download album from Spotify."""
    tracks = album_info(url)
    time.sleep(1)
    logger.info("Now downloading album")
    return dl_track(tracks, save_path)
