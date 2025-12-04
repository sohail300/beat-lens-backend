"""Utility functions for file operations and ID generation."""
import os
import shutil
import random
import time
from typing import Dict, Any


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


def move_file(source_path: str, destination_path: str) -> None:
    """Move a file from source to destination."""
    shutil.move(source_path, destination_path)


def generate_unique_id() -> int:
    """Generate a unique 32-bit ID."""
    random.seed(time.time())
    return random.randint(0, 2**32 - 1)


def generate_song_key(song_title: str, song_artist: str) -> str:
    """Generate a unique key for a song."""
    return f"{song_title}---{song_artist}"


def extend_map(dest: Dict[Any, Any], src: Dict[Any, Any]) -> None:
    """Extend destination map with source map."""
    dest.update(src)

