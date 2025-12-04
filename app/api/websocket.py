"""WebSocket endpoints."""
from fastapi import WebSocket, WebSocketDisconnect
import json
import base64
from datetime import datetime
from app.models.schemas import RecordData
from app.db.session import SessionLocal
from app.services.db_service import total_songs, get_song_by_key
from app.services.spotify_downloader import dl_single_track, dl_playlist, dl_album
from app.services.spotify import track_info, playlist_info, album_info
from app.services.audio import write_wav_file
from app.core.matching import find_matches_fgp
from app.utils.helpers import generate_song_key
from app.config import SONGS_DIR
from app.utils.logger import logger


class ConnectionManager:
    """Manage WebSocket connections."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {websocket.client}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected: {websocket.client}")
    


manager = ConnectionManager()


def download_status(status_type: str, message: str) -> str:
    """Create download status message."""
    data = {"type": status_type, "message": message}
    return json.dumps(data)


async def handle_total_songs(websocket: WebSocket):
    """Handle totalSongs event."""
    db = SessionLocal()
    try:
        total = total_songs(db)
        await websocket.send_text(json.dumps(total))
    except Exception as e:
        logger.error(f"Error getting total songs: {e}")
    finally:
        db.close()


async def handle_song_download(websocket: WebSocket, spotify_url: str):
    """Handle newDownload event."""
    try:
        if "album" in spotify_url:
            tracks = album_info(spotify_url)
            status_msg = f"{len(tracks)} songs found in album."
            await websocket.send_text(download_status("info", status_msg))
            
            total = dl_album(spotify_url, SONGS_DIR)
            status_msg = f"{total} songs downloaded from album"
            await websocket.send_text(download_status("success", status_msg))
        
        elif "playlist" in spotify_url:
            tracks = playlist_info(spotify_url)
            status_msg = f"{len(tracks)} songs found in playlist."
            await websocket.send_text(download_status("info", status_msg))
            
            total = dl_playlist(spotify_url, SONGS_DIR)
            status_msg = f"{total} songs downloaded from playlist."
            await websocket.send_text(download_status("success", status_msg))
        
        elif "track" in spotify_url:
            track = track_info(spotify_url)
            
            # Check if track already exists
            db = SessionLocal()
            try:
                key = generate_song_key(track.title, track.artist)
                song, song_exists = get_song_by_key(db, key)
                if song_exists:
                    status_msg = (
                        f"'{song.title}' by '{song.artist}' already exists in the database "
                        f"(https://www.youtube.com/watch?v={song.youtube_id})"
                    )
                    await websocket.send_text(download_status("error", status_msg))
                    return
            finally:
                db.close()
            
            total = dl_single_track(spotify_url, SONGS_DIR)
            if total != 1:
                status_msg = f"'{track.title}' by '{track.artist}' failed to download"
                await websocket.send_text(download_status("error", status_msg))
            else:
                status_msg = f"'{track.title}' by '{track.artist}' was downloaded"
                await websocket.send_text(download_status("success", status_msg))
        else:
            await websocket.send_text(download_status("error", "Invalid Spotify URL"))
    except Exception as e:
        error_msg = str(e)
        if len(error_msg) <= 25:
            await websocket.send_text(download_status("error", error_msg))
        else:
            logger.error(f"Error downloading song: {e}")


async def handle_new_recording(websocket: WebSocket, record_data: str):
    """Handle newRecording event."""
    try:
        data = json.loads(record_data)
        rec_data = RecordData(**data)
        
        now = datetime.now()
        file_name = (
            f"{now.second:04d}_{now.minute:02d}_{now.hour:02d}_"
            f"{now.day:02d}_{now.month:02d}_{now.year:04d}.wav"
        )
        file_path = f"recordings/{file_name}"
        
        decoded_audio_data = base64.b64decode(rec_data.audio)
        
        write_wav_file(
            file_path,
            decoded_audio_data,
            rec_data.sample_rate,
            rec_data.channels,
            rec_data.sample_size
        )
    except Exception as e:
        logger.error(f"Error handling recording: {e}")


async def handle_new_fingerprint(websocket: WebSocket, fingerprint_data: str):
    """Handle newFingerprint event."""
    db = SessionLocal()
    try:
        data = json.loads(fingerprint_data)
        fingerprint = data.get("fingerprint", {})
        
        # Convert keys to int
        fingerprint_dict = {int(k): int(v) for k, v in fingerprint.items()}
        
        matches, _ = find_matches_fgp(db, fingerprint_dict)
        
        # Limit to top 10 matches
        top_matches = matches[:10]
        
        json_data = json.dumps([match.dict() for match in top_matches])
        await websocket.send_text(json_data)
    except Exception as e:
        logger.error(f"Error handling fingerprint: {e}")
    finally:
        db.close()


async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            event = message.get("event")
            payload = message.get("data", "")
            
            if event == "totalSongs":
                await handle_total_songs(websocket)
            elif event == "newDownload":
                await handle_song_download(websocket, payload)
            elif event == "newRecording":
                await handle_new_recording(websocket, payload)
            elif event == "newFingerprint":
                await handle_new_fingerprint(websocket, payload)
            else:
                logger.warning(f"Unknown event: {event}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

