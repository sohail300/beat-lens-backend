"""Match finding and scoring algorithms."""
import time
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from app.models.schemas import Match, Song
from app.services.db_service import get_couples, get_song_by_id
from app.utils.logger import logger


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
    target_zones: Dict[int, Dict[int, int]] = {}  # songID -> timestamp -> count
    
    for address, couples in couples_map.items():
        sample_time = sample_fingerprint[address]
        for couple in couples:
            song_id = couple.song_id
            db_time = couple.anchor_time_ms
            
            if song_id not in matches:
                matches[song_id] = []
            matches[song_id].append((sample_time, db_time))
            
            if song_id not in timestamps or db_time < timestamps[song_id]:
                timestamps[song_id] = db_time
            
            if song_id not in target_zones:
                target_zones[song_id] = {}
            if db_time not in target_zones[song_id]:
                target_zones[song_id][db_time] = 0
            target_zones[song_id][db_time] += 1
    
    # Calculate scores
    scores = analyze_relative_timing(matches)
    
    # Build match list
    match_list = []
    for song_id, points in scores.items():
        song, song_exists = get_song_by_id(db, song_id)
        if not song_exists:
            logger.info(f"Song with ID ({song_id}) doesn't exist")
            continue
        
        match = Match(
            song_id=song_id,
            song_title=song.title,
            song_artist=song.artist,
            youtube_id=song.youtube_id,
            timestamp=timestamps.get(song_id, 0),
            score=points
        )
        match_list.append(match)
    
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

