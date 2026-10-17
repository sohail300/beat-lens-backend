"""YouTube integration for downloading audio."""
import os
import subprocess
from typing import Optional
from app.models.schemas import Track
from app.utils.logger import logger

SEARCH_RESULTS = 10
DURATION_THRESHOLD = 5  # seconds


def get_youtube_id(track: Track) -> Optional[str]:
    """Get YouTube video ID for a track, preferring a result whose duration matches."""
    try:
        import yt_dlp

        search_query = f"ytsearch{SEARCH_RESULTS}:{track.title} {track.artist}"

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(search_query, download=False)

        entries = [e for e in (search_results or {}).get('entries') or [] if e and e.get('id')]
        if not entries:
            return None

        # Try to find match by duration
        for entry in entries:
            duration = entry.get('duration')
            if duration is not None and abs(duration - track.duration) <= DURATION_THRESHOLD:
                return entry['id']

        # Return first result if no duration match
        return entries[0]['id']
    except Exception as e:
        logger.error(f"Error getting YouTube ID: {e}")
        return None


def download_yt_audio(video_url: str, output_file_path: str) -> str:
    """Download audio from YouTube using yt-dlp. Returns the path of the WAV file."""
    if not os.path.isdir(os.path.dirname(output_file_path)):
        raise ValueError("Output directory does not exist")

    audio_fmt = "wav"
    cmd = [
        "yt-dlp",
        "-f", "bestaudio",
        "--extract-audio",
        "--audio-format", audio_fmt,
        "--no-playlist",
        "-o", output_file_path + ".%(ext)s",
        video_url
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp is not installed or not in PATH")

    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp command failed: {result.stderr[-500:]}")

    return output_file_path + "." + audio_fmt
