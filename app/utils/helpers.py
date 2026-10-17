"""Utility functions for file operations and ID generation."""
import os
import secrets
import shutil
import time


def create_folder(folder_path: str) -> None:
    """Create a folder if it doesn't exist."""
    os.makedirs(folder_path, exist_ok=True)


def delete_file(file_path: str) -> None:
    """Delete a file if it exists."""
    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        else:
            os.remove(file_path)


def delete_old_files(folder: str, max_age_seconds: float) -> int:
    """Delete files in folder last modified more than max_age_seconds ago. Returns how many were deleted."""
    if not os.path.isdir(folder):
        return 0
    cutoff = time.time() - max_age_seconds
    deleted = 0
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted += 1
        except OSError:
            pass  # In use or already gone
    return deleted


def move_file(source_path: str, destination_path: str) -> None:
    """Move a file from source to destination, overwriting it if present."""
    os.replace(source_path, destination_path)


def generate_unique_id() -> int:
    """
    Generate a random song ID.
    Kept below 2**53 so it stays exact when parsed as a JavaScript number.
    """
    return secrets.randbits(52)


def generate_song_key(song_title: str, song_artist: str) -> str:
    """Generate a unique key for a song."""
    return f"{song_title}---{song_artist}"


def correct_filename(title: str, artist: str) -> tuple[str, str]:
    """Strip characters that aren't allowed in file names."""
    invalid_chars = ['<', '>', ':', '"', '\\', '/', '|', '?', '*']
    for char in invalid_chars:
        title = title.replace(char, '')
        artist = artist.replace(char, '')
    return title.strip(), artist.strip()


def song_file_path(title: str, artist: str) -> str:
    """Where a song's WAV file lives: <SONGS_DIR>/<Title> - <Artist>.wav"""
    from app.config import SONGS_DIR

    title, artist = correct_filename(title, artist)
    return os.path.join(SONGS_DIR, f"{title} - {artist}.wav")
