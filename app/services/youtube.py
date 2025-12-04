"""YouTube integration for downloading audio."""
import os
import subprocess
import re
from typing import Optional
from app.models.schemas import Track
from app.utils.logger import logger


def get_youtube_id(track: Track) -> Optional[str]:
    """Get YouTube video ID for a track."""
    try:
        import yt_dlp
        
        search_query = f"'{track.title}' {track.artist}"
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            'max_results': 10
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(search_query, download=False)
            
            if not search_results or 'entries' not in search_results:
                return None
            
            entries = search_results['entries']
            if not entries:
                return None
            
            # Try to find match by duration
            duration_threshold = 5  # seconds
            for entry in entries:
                if 'duration' in entry:
                    duration = entry['duration']
                    if abs(duration - track.duration) <= duration_threshold:
                        return entry['id']
            
            # Return first result if no duration match
            if entries:
                return entries[0]['id']
        
        return None
    except Exception as e:
        logger.error(f"Error getting YouTube ID: {e}")
        return None


def download_yt_audio(video_url: str, output_file_path: str) -> str:
    """Download audio from YouTube using yt-dlp."""
    if not os.path.isdir(os.path.dirname(output_file_path)):
        raise ValueError("Output directory does not exist")
    
    # Check if yt-dlp is available
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("yt-dlp is not installed or not in PATH")
    
    audio_fmt = "wav"
    cmd = [
        "yt-dlp",
        "-f", "bestaudio",
        "--extract-audio",
        "--audio-format", audio_fmt,
        "-o", output_file_path,
        video_url
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp command failed: {result.stderr}")
    
    return output_file_path + "." + audio_fmt

