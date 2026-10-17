"""Spectrogram generation using STFT."""
from typing import List

import numpy as np
from scipy.signal import lfilter

from app.core.fft import fft


# Constants matching Go implementation
DSP_RATIO = 4
WINDOW_SIZE = 1024
MAX_FREQ = 5000.0  # 5kHz
HOP_SIZE = WINDOW_SIZE // 2  # 50% overlap
WINDOW_TYPE = "hanning"

# Frequency-bin bands used for peak picking
BANDS = [(0, 10), (10, 20), (20, 40), (40, 80), (80, 160), (160, 512)]


class Peak:
    """Represents a significant point in the spectrogram."""
    def __init__(self, freq: float, time: float, bin: int):
        self.freq = freq  # Hz
        self.time = time  # seconds
        self.bin = bin    # FFT bin index, 0 .. WINDOW_SIZE // 2 - 1


def spectrogram(sample: np.ndarray, sample_rate: int) -> np.ndarray:
    """
    Generate spectrogram from audio samples.
    Returns an array of shape (frames, WINDOW_SIZE // 2) of magnitudes.
    """
    # Low-pass filter
    filtered_sample = low_pass_filter(MAX_FREQ, float(sample_rate), sample)

    # Downsample
    downsampled_sample = downsample(filtered_sample, sample_rate, sample_rate // DSP_RATIO)

    num_frames = (len(downsampled_sample) - WINDOW_SIZE) // HOP_SIZE + 1
    if num_frames <= 0:
        return np.empty((0, WINDOW_SIZE // 2))

    # Slice overlapping frames and apply window
    starts = np.arange(num_frames) * HOP_SIZE
    frames = downsampled_sample[starts[:, None] + np.arange(WINDOW_SIZE)]
    frames = frames * create_window(WINDOW_SIZE, WINDOW_TYPE)

    # Perform FFT and keep the magnitude of the positive frequencies
    return np.abs(fft(frames)[:, :WINDOW_SIZE // 2])


def low_pass_filter(cutoff_frequency: float, sample_rate: float, input_data: np.ndarray) -> np.ndarray:
    """
    First-order low-pass filter that attenuates high frequencies.
    Uses transfer function H(s) = 1 / (1 + sRC), i.e.
    y[i] = alpha * x[i] + (1 - alpha) * y[i - 1]
    """
    rc = 1.0 / (2 * np.pi * cutoff_frequency)
    dt = 1.0 / sample_rate
    alpha = dt / (rc + dt)

    return lfilter([alpha], [1.0, -(1.0 - alpha)], np.asarray(input_data, dtype=np.float64))


def downsample(input_data: np.ndarray, original_sample_rate: int, target_sample_rate: int) -> np.ndarray:
    """Downsample audio by averaging blocks of samples."""
    if target_sample_rate <= 0 or original_sample_rate <= 0:
        raise ValueError("Sample rates must be positive")
    if target_sample_rate > original_sample_rate:
        raise ValueError("Target sample rate must be less than or equal to original")

    ratio = original_sample_rate // target_sample_rate
    if ratio <= 0:
        raise ValueError("Invalid ratio calculated from sample rates")

    data = np.asarray(input_data, dtype=np.float64)
    full_blocks = len(data) // ratio
    resampled = data[:full_blocks * ratio].reshape(full_blocks, ratio).mean(axis=1)

    # Average the trailing partial block, if any
    remainder = data[full_blocks * ratio:]
    if len(remainder):
        resampled = np.append(resampled, remainder.mean())

    return resampled


def create_window(window_size: int, window_type: str) -> np.ndarray:
    """Create window function (Hanning or Hamming)."""
    theta = 2 * np.pi * np.arange(window_size) / (window_size - 1)
    if window_type == "hamming":
        return 0.54 - 0.46 * np.cos(theta)
    return 0.5 - 0.5 * np.cos(theta)  # Hanning (default)


def extract_peaks(spectrogram_data: np.ndarray, sample_rate: int) -> List[Peak]:
    """Extract significant peaks from spectrogram."""
    if len(spectrogram_data) < 1:
        return []

    # Exact time between frames. (Dividing the audio's duration by the frame count instead gives a
    # slightly different value for every clip length, so the same audio got different hashes.)
    frame_duration = HOP_SIZE / (float(sample_rate) / DSP_RATIO)

    # Calculate frequency resolution
    effective_sample_rate = float(sample_rate) / DSP_RATIO
    freq_resolution = effective_sample_rate / WINDOW_SIZE

    # Strongest bin within each band, for every frame: shape (frames, bands)
    max_mags = np.stack(
        [spectrogram_data[:, lo:hi].max(axis=1) for lo, hi in BANDS], axis=1
    )
    freq_indices = np.stack(
        [spectrogram_data[:, lo:hi].argmax(axis=1) + lo for lo, hi in BANDS], axis=1
    )

    # Keep the bands that exceed the frame's average band maximum
    avg = max_mags.mean(axis=1, keepdims=True)
    frame_idx, band_idx = np.nonzero(max_mags > avg)

    return [
        Peak(
            freq=float(freq_indices[f, b] * freq_resolution),
            time=float(f * frame_duration),
            bin=int(freq_indices[f, b]),
        )
        for f, b in zip(frame_idx, band_idx)
    ]
