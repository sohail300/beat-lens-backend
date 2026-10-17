"""Match finding and scoring algorithms."""
import time
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from app.config import MIN_MATCH_RATIO, MIN_MATCH_SCORE
from app.models.schemas import Match
from app.services.db_service import get_couples, get_songs_by_ids


def find_matches_fgp(db: Session, sample_fingerprint: Dict[int, int]) -> Tuple[List[Match], float]:
    """
    Use sample fingerprint to find matching songs in database.
    Returns (matches, search_duration_seconds).
    """
    start_time = time.time()

    addresses = list(sample_fingerprint.keys())

    couples_map = get_couples(db, addresses)

    # matches: songID -> [(sampleTime, dbTime)]
    matches: Dict[int, List[Tuple[int, int]]] = {}
    timestamps: Dict[int, int] = {}  # songID -> earliest timestamp

    for address, couples in couples_map.items():
        sample_time = sample_fingerprint[address]
        for couple in couples:
            song_id = couple.song_id
            db_time = couple.anchor_time_ms

            matches.setdefault(song_id, []).append((sample_time, db_time))

            if song_id not in timestamps or db_time < timestamps[song_id]:
                timestamps[song_id] = db_time

    # Calculate scores
    scores = analyze_relative_timing(matches)

    # Build match list
    songs = get_songs_by_ids(db, list(scores.keys()))
    match_list = [
        Match(
            song_id=song_id,
            song_title=songs[song_id].title,
            song_artist=songs[song_id].artist,
            youtube_id=songs[song_id].youtube_id,
            timestamp=timestamps.get(song_id, 0),
            score=points,
        )
        for song_id, points in scores.items()
        if song_id in songs
    ]

    # Sort by score (descending)
    match_list.sort(key=lambda x: x.score, reverse=True)

    search_duration = time.time() - start_time
    return match_list, search_duration


def analyze_relative_timing(matches: Dict[int, List[Tuple[int, int]]]) -> Dict[int, float]:
    """
    Calculate score for each song based on consistency of time offsets
    between sample and database.
    """
    scores: Dict[int, float] = {}

    for song_id, times in matches.items():
        offset_counts: Dict[int, int] = {}

        for sample_time, db_time in times:
            offset = db_time - sample_time
            # Bin offsets in 100ms buckets
            offset_bucket = offset // 100
            offset_counts[offset_bucket] = offset_counts.get(offset_bucket, 0) + 1

        # Find max count
        max_count = max(offset_counts.values()) if offset_counts else 0
        scores[song_id] = float(max_count)

    return scores


def confident_match(matches: List[Match]) -> List[Match]:
    """
    Keep the best match only if it clearly stands out; otherwise report nothing.
    Every sample shares a few fingerprints with unrelated songs by chance, so the
    raw ranking always has a "winner" even for songs that aren't in the library.
    """
    if not matches:
        return []
    best = matches[0]
    runner_up = matches[1].score if len(matches) > 1 else 0.0
    if best.score >= MIN_MATCH_SCORE and best.score >= MIN_MATCH_RATIO * max(runner_up, 1.0):
        return [best]
    return []
