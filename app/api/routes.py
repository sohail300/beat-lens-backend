"""REST API endpoints."""
from fastapi import APIRouter, HTTPException, Form
from typing import Optional
import os
import math
import shutil
from app.models.schemas import (
    FindRequest, DownloadRequest, SaveRequest, EraseRequest,
    Match
)
from app.services.audio import read_wav_info
from app.core.spectrogram import spectrogram, extract_peaks
from app.core.fingerprinting import fingerprint
from app.services.youtube import get_youtube_id
from app.models.schemas import Track
from app.services.spotify_downloader import process_and_save_song
from app.utils.helpers import move_file
from app.db.session import db_dependency
from app.services.db_service import total_songs, delete_collection
from app.services.spotify_downloader import dl_single_track, dl_playlist, dl_album
from app.services.spotify import track_info, playlist_info, album_info
from app.services.audio import fingerprint_audio, convert_to_wav, get_metadata
from app.core.matching import find_matches_fgp
from app.config import SONGS_DIR
from app.utils.helpers import create_folder, generate_song_key
from app.utils.logger import logger

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/songs/total")
async def get_total_songs(db: db_dependency):
    """Get total number of songs in database."""
    total = total_songs(db)
    return {"total": total}


@router.post("/find")
async def find_matches(request: FindRequest, db: db_dependency):
    """Find matches for audio file or fingerprint."""
    try:
        if request.file_path:
            # Process audio file
            wav_file_path = convert_to_wav(request.file_path)
            wav_info = read_wav_info(wav_file_path)
            spectro = spectrogram(wav_info.left_channel_samples, wav_info.sample_rate)
            peaks = extract_peaks(spectro, wav_info.duration, wav_info.sample_rate)
            sample_fingerprint_map = fingerprint(peaks, 0)  # Temporary ID
            
            # Convert to format expected by find_matches_fgp
            fingerprint_dict = {
                address: couple.anchor_time_ms
                for address, couple in sample_fingerprint_map.items()
            }
        elif request.fingerprint:
            fingerprint_dict = request.fingerprint
        else:
            raise HTTPException(status_code=400, detail="Either file_path or fingerprint must be provided")
        
        matches, search_duration = find_matches_fgp(db, fingerprint_dict)
        
        # Limit to top 20 matches
        top_matches = matches[:20]
        
        return {
            "matches": [match.dict() for match in top_matches],
            "search_duration": search_duration
        }
    except Exception as e:
        logger.error(f"Error finding matches: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download")
async def download_from_spotify(request: DownloadRequest):
    """Download from Spotify URL."""
    try:
        spotify_url = request.spotify_url
        create_folder(SONGS_DIR)
        
        if "album" in spotify_url:
            total = dl_album(spotify_url, SONGS_DIR)
        elif "playlist" in spotify_url:
            total = dl_playlist(spotify_url, SONGS_DIR)
        elif "track" in spotify_url:
            total = dl_single_track(spotify_url, SONGS_DIR)
        else:
            raise HTTPException(status_code=400, detail="Invalid Spotify URL")
        
        return {"total_downloaded": total}
    except Exception as e:
        logger.error(f"Error downloading: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_song(
    file_path: str = Form(...),
    force: bool = Form(False)
):
    """Save local audio file to database."""
    try:
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Get metadata
        metadata = get_metadata(file_path)
        tags = metadata.get("format", {}).get("tags", {})
        
        duration_str = metadata.get("format", {}).get("duration", "0")
        try:
            duration_float = float(duration_str)
        except ValueError:
            duration_float = 0.0
        
        track_title = tags.get("title", "")
        track_artist = tags.get("artist", "")
        track_album = tags.get("album", "")
        
        # If title is empty, use filename
        if not track_title:
            track_title = os.path.splitext(os.path.basename(file_path))[0]
        
        if not track_artist:
            raise HTTPException(status_code=400, detail="No artist found in metadata")
        
        # Get YouTube ID
        track = Track(
            title=track_title,
            artist=track_artist,
            album=track_album,
            duration=int(math.round(duration_float))
        )
        
        yt_id = None
        try:
            yt_id = get_youtube_id(track)
        except Exception as e:
            if not force:
                raise HTTPException(status_code=400, detail=f"Failed to get YouTube ID: {e}")
        
        # Process and save
        process_and_save_song(file_path, track_title, track_artist, yt_id or "")
        
        # Move to songs directory
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        wav_file = file_name + ".wav"
        source_path = os.path.join(os.path.dirname(file_path), wav_file)
        new_file_path = os.path.join(SONGS_DIR, wav_file)
        
        if os.path.exists(source_path):
            from app.utils.helpers import move_file
            move_file(source_path, new_file_path)
        
        return {"status": "saved"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving song: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/erase")
async def erase_data(request: EraseRequest, db: db_dependency):
    """Erase database and/or song files."""
    try:
        delete_collection(db, "fingerprints")
        delete_collection(db, "songs")
        
        if request.all:
            # Delete song files
            if os.path.exists(SONGS_DIR):
                for file in os.listdir(SONGS_DIR):
                    file_path = os.path.join(SONGS_DIR, file)
                    if os.path.isfile(file_path):
                        ext = os.path.splitext(file)[1]
                        if ext in [".wav", ".m4a"]:
                            os.remove(file_path)
        
        return {"status": "erased"}
    except Exception as e:
        logger.error(f"Error erasing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

