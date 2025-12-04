"""Spotify API integration."""
import os
import json
import time
import re
import requests
from typing import List, Optional
from app.models.schemas import Track
from app.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
from app.utils.logger import logger

TOKEN_URL = "https://accounts.spotify.com/api/token"
CACHED_TOKEN_PATH = "token.json"


class CachedToken:
    """Cached Spotify access token."""
    def __init__(self, token: str, expires_at: float):
        self.token = token
        self.expires_at = expires_at


def load_cached_token() -> Optional[str]:
    """Load cached token if still valid."""
    if not os.path.exists(CACHED_TOKEN_PATH):
        return None
    
    try:
        with open(CACHED_TOKEN_PATH, 'r') as f:
            data = json.load(f)
            expires_at = data.get("expires_at", 0)
            if time.time() < expires_at:
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
    
    response = requests.post(TOKEN_URL, data=data)
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
    
    response = requests.get(endpoint, headers=headers)
    return response.status_code, response.text


def get_id(url: str) -> str:
    """Extract ID from Spotify URL."""
    parts = url.split("/")
    if len(parts) < 5:
        raise ValueError("Invalid Spotify URL")
    id_part = parts[4].split("?")[0]
    return id_part


def track_info(url: str) -> Track:
    """Get track information from Spotify URL."""
    pattern = r'open\.spotify\.com\/(?:intl-.+\/)?track\/([a-zA-Z0-9]{22})(\?si=[a-zA-Z0-9]{16})?'
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
    pattern = r'open\.spotify\.com\/playlist\/([a-zA-Z0-9]{22})'
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
            track_data = item.get("track", {})
            if not track_data:
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
    pattern = r'open\.spotify\.com\/album\/([a-zA-Z0-9]{22})'
    match = re.search(pattern, url)
    if not match:
        raise ValueError("Invalid album URL")
    
    album_id = match.group(1)
    endpoint = f"https://api.spotify.com/v1/albums/{album_id}/tracks?limit=50"
    status_code, json_response = request(endpoint)
    
    if status_code != 200:
        raise RuntimeError(f"Non-200 status: {status_code}")
    
    data = json.loads(json_response)
    tracks = []
    
    for item in data.get("items", []):
        artists = [artist["name"] for artist in item.get("artists", [])]
        tracks.append(Track(
            title=item["name"],
            artist=artists[0] if artists else "",
            album="",
            artists=artists,
            duration=item["duration_ms"] // 1000
        ))
    
    return tracks


def song_key_exists(key: str, db=None) -> bool:
    """Check if song key exists in database."""
    from sqlalchemy.orm import Session
    from app.db.session import SessionLocal
    from app.services.db_service import get_song_by_key
    
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    
    try:
        _, exists = get_song_by_key(db, key)
        return exists
    finally:
        if should_close:
            db.close()


def yt_id_exists(yt_id: str, db=None) -> bool:
    """Check if YouTube ID exists in database."""
    from sqlalchemy.orm import Session
    from app.db.session import SessionLocal
    from app.services.db_service import get_song_by_ytid
    
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    
    try:
        _, exists = get_song_by_ytid(db, yt_id)
        return exists
    finally:
        if should_close:
            db.close()

