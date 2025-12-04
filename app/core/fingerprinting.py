"""Audio fingerprinting algorithm."""
from typing import Dict, List
from app.core.spectrogram import Peak
from app.models.schemas import Couple


# Constants matching Go implementation
MAX_FREQ_BITS = 9
MAX_DELTA_BITS = 14
TARGET_ZONE_SIZE = 5


def fingerprint(peaks: List[Peak], song_id: int) -> Dict[int, Couple]:
    """
    Generate fingerprints from a list of peaks.
    Each fingerprint consists of an address and a couple.
    """
    fingerprints: Dict[int, Couple] = {}
    
    for i, anchor in enumerate(peaks):
        for j in range(i + 1, min(len(peaks), i + TARGET_ZONE_SIZE + 1)):
            target = peaks[j]
            
            address = create_address(anchor, target)
            anchor_time_ms = int(anchor.time * 1000)
            
            fingerprints[address] = Couple(
                anchor_time_ms=anchor_time_ms,
                song_id=song_id
            )
    
    return fingerprints


def create_address(anchor: Peak, target: Peak) -> int:
    """
    Generate a unique address for a pair of anchor and target points.
    The address is a 32-bit integer where:
    - 9 bits represent anchor frequency
    - 9 bits represent target frequency
    - 14 bits represent time difference (delta time)
    """
    anchor_freq_bin = int(anchor.freq / 10)  # Scale down to fit in 9 bits
    target_freq_bin = int(target.freq / 10)
    
    delta_ms_raw = int((target.time - anchor.time) * 1000)
    
    # Mask to fit within bit constraints
    anchor_freq_bits = anchor_freq_bin & ((1 << MAX_FREQ_BITS) - 1)  # 9 bits
    target_freq_bits = target_freq_bin & ((1 << MAX_FREQ_BITS) - 1)  # 9 bits
    delta_bits = delta_ms_raw & ((1 << MAX_DELTA_BITS) - 1)  # 14 bits
    
    # Combine into 32-bit address
    address = (anchor_freq_bits << 23) | (target_freq_bits << 14) | delta_bits
    
    return address

