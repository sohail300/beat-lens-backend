"""Spotify API integration."""
import os
import json
import time
import re
import requests
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.schemas import Track
from app.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, TMP_DIR
from app.utils.helpers import create_folder

TOKEN_URL = "https://accounts.spotify.com/api/token"
CACHED_TOKEN_PATH = os.path.join(TMP_DIR, "spotify_token.json")
REQUEST_TIMEOUT = 15  # seconds

def load_cached_token() -> Optional[str]:
    """Load cached token if still valid."""
    if not os.path.exists(CACHED_TOKEN_PATH):
        return None
    
    try:
        with open(CACHED_TOKEN_PATH, 'r') as f:
            data = json.load(f)
            expires_at = data.get("expires_at", 0)
            # Refresh a minute early so the token can't expire mid-request
            if time.time() < expires_at - 60:
                return data.get("token")
    except Exception:
        pass
    return None


def save_token(token: str, expires_in: int) -> None:
    """Save token to cache."""
    cached = {
        "token": token,
        "expires_at": time.time() + expires_in
    }
    create_folder(TMP_DIR)
    with open(CACHED_TOKEN_PATH, 'w') as f:
        json.dump(cached, f)


def access_token() -> str:
    """Get Spotify access token."""
    # Try cached token first
    token = load_cached_token()
    if token:
        return token
    
    # Request new token
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise ValueError("SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET not set")
    
    data = {
        "grant_type": "client_credentials",
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET
    }
    
    response = requests.post(TOKEN_URL, data=data, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        raise RuntimeError(f"Token request failed: {response.text}")
    
    token_data = response.json()
    token = token_data["access_token"]
    expires_in = token_data["expires_in"]
    
    save_token(token, expires_in)
    return token


def request(endpoint: str) -> tuple[int, str]:
    """Make authenticated request to Spotify API."""
    token = access_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(endpoint, headers=headers, timeout=REQUEST_TIMEOUT)
    return response.status_code, response.text


def track_info(url: str) -> Track:
    """Get track information from Spotify URL."""
    pattern = r'open\.spotify\.com\/(?:intl-[^/]+\/)?track\/([a-zA-Z0-9]{22})'
    match = re.search(pattern, url)
    if not match:
        raise ValueError("Invalid track URL")
    
    track_id = match.group(1)
    endpoint = f"https://api.spotify.com/v1/tracks/{track_id}"
    status_code, json_response = request(endpoint)
    
    if status_code != 200:
        raise RuntimeError(f"Non-200 status code: {status_code}")
    
    data = json.loads(json_response)
    artists = [artist["name"] for artist in data["artists"]]
    
    return Track(
        title=data["name"],
        artist=artists[0] if artists else "",
        album=data["album"]["name"],
        artists=artists,
        duration=data["duration_ms"] // 1000
    )


def playlist_info(url: str) -> List[Track]:
    """Get playlist information from Spotify URL."""
    pattern = r'open\.spotify\.com\/(?:intl-[^/]+\/)?playlist\/([a-zA-Z0-9]{22})'
    match = re.search(pattern, url)
    if not match:
        raise ValueError("Invalid playlist URL")
    
    playlist_id = match.group(1)
    all_tracks = []
    offset = 0
    limit = 100
    
    while True:
        endpoint = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks?offset={offset}&limit={limit}"
        status_code, json_response = request(endpoint)
        
        if status_code != 200:
            raise RuntimeError(f"Non-200 status: {status_code}")
        
        data = json.loads(json_response)
        items = data.get("items", [])
        
        for item in items:
            track_data = item.get("track")
            # Skip removed tracks and local files (they have no usable metadata)
            if not track_data or track_data.get("is_local"):
                continue
            
            artists = [artist["name"] for artist in track_data.get("artists", [])]
            all_tracks.append(Track(
                title=track_data["name"],
                artist=artists[0] if artists else "",
                album=track_data.get("album", {}).get("name", ""),
                artists=artists,
                duration=track_data["duration_ms"] // 1000
            ))
        
        offset += limit
        if offset >= data.get("total", 0):
            break
    
    return all_tracks


def album_info(url: str) -> List[Track]:
    """Get album information from Spotify URL."""
    pattern = r'open\.spotify\.com\/(?:intl-[^/]+\/)?album\/([a-zA-Z0-9]{22})'
    match = re.search(pattern, url)
    if not match:
        raise ValueError("Invalid album URL")
    
    album_id = match.group(1)
    status_code, json_response = request(f"https://api.spotify.com/v1/albums/{album_id}")
    if status_code != 200:
        raise RuntimeError(f"Non-200 status: {status_code}")

    data = json.loads(json_response)
    album_name = data.get("name", "")
    page = data.get("tracks", {})
    tracks = []

    while True:
        for item in page.get("items", []):
            artists = [artist["name"] for artist in item.get("artists", [])]
            tracks.append(Track(
                title=item["name"],
                artist=artists[0] if artists else "",
                album=album_name,
                artists=artists,
                duration=item["duration_ms"] // 1000
            ))

        next_url = page.get("next")
        if not next_url:
            break
        status_code, json_response = request(next_url)
        if status_code != 200:
            raise RuntimeError(f"Non-200 status: {status_code}")
        page = json.loads(json_response)

    return tracks


def song_key_exists(key: str, db: Optional[Session] = None) -> bool:
    """Check if song key exists in database."""
    from app.db.session import SessionLocal
    from app.services.db_service import get_song_by_key

    should_close = db is None
    if db is None:
        db = SessionLocal()

    try:
        _, exists = get_song_by_key(db, key)
        return exists
    finally:
        if should_close:
            db.close()


def yt_id_exists(yt_id: str, db: Optional[Session] = None) -> bool:
    """Check if YouTube ID exists in database."""
    from app.db.session import SessionLocal
    from app.services.db_service import get_song_by_ytid

    should_close = db is None
    if db is None:
        db = SessionLocal()

    try:
        _, exists = get_song_by_ytid(db, yt_id)
        return exists
    finally:
        if should_close:
            db.close()
