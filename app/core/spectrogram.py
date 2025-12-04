"""Spectrogram generation using STFT."""
import numpy as np
from typing import List, Tuple
from app.core.fft import fft


# Constants matching Go implementation
DSP_RATIO = 4
WINDOW_SIZE = 1024
MAX_FREQ = 5000.0  # 5kHz
HOP_SIZE = WINDOW_SIZE // 2  # 50% overlap
WINDOW_TYPE = "hanning"


class Peak:
    """Represents a significant point in the spectrogram."""
    def __init__(self, freq: float, time: float):
        self.freq = freq
        self.time = time


def spectrogram(sample: List[float], sample_rate: int) -> List[List[float]]:
    """Generate spectrogram from audio samples."""
    # Low-pass filter
    filtered_sample = low_pass_filter(MAX_FREQ, float(sample_rate), sample)
    
    # Downsample
    downsampled_sample = downsample(filtered_sample, sample_rate, sample_rate // DSP_RATIO)
    
    # Create window
    window = create_window(WINDOW_SIZE, WINDOW_TYPE)
    
    # Initialize spectrogram
    spectrogram_data = []
    
    # Perform STFT
    for start in range(0, len(downsampled_sample) - WINDOW_SIZE + 1, HOP_SIZE):
        end = start + WINDOW_SIZE
        frame = np.array(downsampled_sample[start:end])
        
        # Apply window
        frame = frame * window
        
        # Perform FFT
        fft_result = fft(frame.tolist())
        
        # Convert complex spectrum to magnitude spectrum
        magnitude = np.abs(fft_result[:len(fft_result) // 2])
        
        spectrogram_data.append(magnitude.tolist())
    
    return spectrogram_data


def low_pass_filter(cutoff_frequency: float, sample_rate: float, input_data: List[float]) -> List[float]:
    """
    First-order low-pass filter that attenuates high frequencies.
    Uses transfer function H(s) = 1 / (1 + sRC)
    """
    rc = 1.0 / (2 * np.pi * cutoff_frequency)
    dt = 1.0 / sample_rate
    alpha = dt / (rc + dt)
    
    filtered_signal = []
    prev_output = 0.0
    
    for i, x in enumerate(input_data):
        if i == 0:
            filtered_signal.append(x * alpha)
        else:
            filtered_signal.append(alpha * x + (1 - alpha) * prev_output)
        prev_output = filtered_signal[i]
    
    return filtered_signal


def downsample(input_data: List[float], original_sample_rate: int, target_sample_rate: int) -> List[float]:
    """Downsample audio from original to target sample rate."""
    if target_sample_rate <= 0 or original_sample_rate <= 0:
        raise ValueError("Sample rates must be positive")
    if target_sample_rate > original_sample_rate:
        raise ValueError("Target sample rate must be less than or equal to original")
    
    ratio = original_sample_rate // target_sample_rate
    if ratio <= 0:
        raise ValueError("Invalid ratio calculated from sample rates")
    
    resampled = []
    for i in range(0, len(input_data), ratio):
        end = min(i + ratio, len(input_data))
        avg = sum(input_data[i:end]) / (end - i)
        resampled.append(avg)
    
    return resampled


def create_window(window_size: int, window_type: str) -> np.ndarray:
    """Create window function (Hanning or Hamming)."""
    window = np.zeros(window_size)
    for i in range(window_size):
        theta = 2 * np.pi * i / (window_size - 1)
        if window_type == "hamming":
            window[i] = 0.54 - 0.46 * np.cos(theta)
        else:  # Hanning (default)
            window[i] = 0.5 - 0.5 * np.cos(theta)
    return window


def extract_peaks(spectrogram_data: List[List[float]], audio_duration: float, sample_rate: int) -> List[Peak]:
    """Extract significant peaks from spectrogram."""
    if len(spectrogram_data) < 1:
        return []
    
    bands = [
        (0, 10), (10, 20), (20, 40), (40, 80), (80, 160), (160, 512)
    ]
    
    peaks = []
    frame_duration = audio_duration / len(spectrogram_data) if len(spectrogram_data) > 0 else 0
    
    # Calculate frequency resolution
    effective_sample_rate = float(sample_rate) / DSP_RATIO
    freq_resolution = effective_sample_rate / WINDOW_SIZE
    
    for frame_idx, frame in enumerate(spectrogram_data):
        max_mags = []
        freq_indices = []
        
        # Find max in each band
        for band_min, band_max in bands:
            max_mag = 0.0
            max_freq_idx = 0
            for idx in range(band_min, min(band_max, len(frame))):
                if frame[idx] > max_mag:
                    max_mag = frame[idx]
                    max_freq_idx = idx
            max_mags.append(max_mag)
            freq_indices.append(max_freq_idx)
        
        # Calculate average magnitude
        avg = sum(max_mags) / len(max_mags) if max_mags else 0
        
        # Add peaks that exceed average
        for i, mag in enumerate(max_mags):
            if mag > avg:
                peak_time = frame_idx * frame_duration
                peak_freq = freq_indices[i] * freq_resolution
                peaks.append(Peak(freq=peak_freq, time=peak_time))
    
    return peaks

