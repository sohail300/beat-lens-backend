"""Spotify download service."""
import os
import subprocess
import time
import concurrent.futures
from typing import List
from app.models.schemas import Track
from app.services.spotify import track_info, playlist_info, album_info, song_key_exists, yt_id_exists
from app.services.youtube import get_youtube_id, download_yt_audio
from app.services.audio import fingerprint_audio, get_metadata
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.services.db_service import (
    register_song, store_fingerprints, delete_song_by_id
)
from app.core.fingerprinting import fingerprint
from app.core.spectrogram import spectrogram, extract_peaks
from app.utils.helpers import generate_song_key, create_folder
from app.config import SONGS_DIR
from app.utils.logger import logger


DELETE_SONG_FILE = False  # Set True to delete song file after fingerprinting


def correct_filename(title: str, artist: str) -> tuple[str, str]:
    """Fix invalid filename characters."""
    invalid_chars = ['<', '>', ':', '"', '\\', '/', '|', '?', '*']
    for char in invalid_chars:
        title = title.replace(char, '')
        artist = artist.replace(char, '')
    return title, artist


def add_tags(file_path: str, track: Track) -> None:
    """Add metadata tags to WAV file using FFmpeg."""
    temp_file = os.path.splitext(file_path)[0] + "2.wav"
    
    cmd = [
        "ffmpeg",
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
        raise RuntimeError(f"Failed to add tags: {result.stderr}")
    
    os.rename(temp_file, file_path)


def process_and_save_song(song_file_path: str, song_title: str, song_artist: str, yt_id: str, db: Session = None) -> None:
    """Process and save song to database."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    
    song_id = None
    try:
        song_id = register_song(db, song_title, song_artist, yt_id)
        
        # Generate fingerprint
        fingerprints = fingerprint_audio(song_file_path, song_id)
        
        # Convert to Couple format
        from app.models.schemas import Couple
        fingerprint_dict = {
            address: Couple(anchor_time_ms=couple.anchor_time_ms, song_id=couple.song_id)
            for address, couple in fingerprints.items()
        }
        
        store_fingerprints(db, fingerprint_dict)
        logger.info(f"Fingerprint for {song_title} by {song_artist} saved in DB successfully")
    except Exception as e:
        if song_id:
            try:
                delete_song_by_id(db, song_id)
            except:
                pass
        raise
    finally:
        if should_close:
            db.close()


def get_yt_id(track: Track) -> str:
    """Get YouTube ID for track, retrying if duplicate."""
    yt_id = get_youtube_id(track)
    if not yt_id:
        raise ValueError(f"Could not get YouTube ID for {track.title} by {track.artist}")
    
    # Check if YouTube ID exists
    if yt_id_exists(yt_id):
        logger.warning(f"YouTube ID ({yt_id}) exists. Trying again...")
        yt_id = get_youtube_id(track)
        if not yt_id:
            raise ValueError(f"Could not get YouTube ID for {track.title} by {track.artist}")
        
        if yt_id_exists(yt_id):
            raise ValueError(f"YouTube ID ({yt_id}) exists")
    
    return yt_id


def dl_track(tracks: List[Track], path: str) -> int:
    """Download tracks from YouTube."""
    create_folder(path)
    total_tracks = 0
    
    def process_track(track: Track):
        nonlocal total_tracks
        # Create a new session for each track (thread-safe)
        db = SessionLocal()
        try:
            # Check if song exists
            key = generate_song_key(track.title, track.artist)
            from app.services.spotify import song_key_exists
            if song_key_exists(key, db):
                logger.info(f"'{track.title}' by '{track.artist}' already exists.")
                return
            
            # Get YouTube ID
            yt_id = get_yt_id(track)
            
            # Correct filename
            title, artist = correct_filename(track.title, track.artist)
            file_name = f"{title} - {artist}"
            file_path = os.path.join(path, file_name)
            
            # Download from YouTube
            video_url = f"https://www.youtube.com/watch?v={yt_id}"
            file_path = download_yt_audio(video_url, file_path)
            
            # Process and save (pass session to avoid creating new one)
            process_and_save_song(file_path, title, artist, yt_id, db)
            
            # Add tags
            wav_file_path = os.path.join(path, file_name + ".wav")
            if os.path.exists(wav_file_path):
                add_tags(wav_file_path, track)
            
            if DELETE_SONG_FILE:
                os.remove(wav_file_path)
            
            logger.info(f"'{track.title}' by '{track.artist}' was downloaded")
            total_tracks += 1
        except Exception as e:
            logger.error(f"Error processing track {track.title}: {e}")
        finally:
            db.close()
    
    # Process tracks with thread pool
    import multiprocessing
    max_workers = multiprocessing.cpu_count()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_track, track) for track in tracks]
        concurrent.futures.wait(futures)
    
    logger.info(f"Total tracks downloaded: {total_tracks}")
    return total_tracks


def dl_single_track(url: str, save_path: str) -> int:
    """Download a single track from Spotify."""
    logger.info(f"Getting track info: {url}")
    track = track_info(url)
    tracks = [track]
    
    logger.info("Now downloading track")
    return dl_track(tracks, save_path)


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

