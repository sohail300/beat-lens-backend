"""Signal processing and fingerprint format."""
import numpy as np

from app.core.fingerprinting import MAX_DELTA_BITS, MAX_FREQ_BITS, create_address, fingerprint
from app.core.spectrogram import (
    WINDOW_SIZE, Peak, create_window, downsample, extract_peaks, low_pass_filter, spectrogram,
)
from tests.conftest import SAMPLE_RATE, make_song


def test_low_pass_filter_matches_reference_recurrence():
    x = np.random.default_rng(0).standard_normal(500)
    rc = 1.0 / (2 * np.pi * 5000.0)
    dt = 1.0 / SAMPLE_RATE
    alpha = dt / (rc + dt)
    expected, prev = [], 0.0
    for i, v in enumerate(x):
        prev = v * alpha if i == 0 else alpha * v + (1 - alpha) * prev
        expected.append(prev)
    np.testing.assert_allclose(low_pass_filter(5000.0, SAMPLE_RATE, x), expected, rtol=1e-12)


def test_downsample_averages_blocks_including_partial_tail():
    np.testing.assert_allclose(downsample(np.arange(10.0), 4, 1), [1.5, 5.5, 8.5])


def test_hanning_window_is_symmetric_and_zero_at_edges():
    w = create_window(WINDOW_SIZE, "hanning")
    assert w[0] == 0 and abs(w[-1]) < 1e-12
    np.testing.assert_allclose(w, w[::-1], atol=1e-12)


def test_spectrogram_shape():
    samples = make_song(1, seconds=3)
    spec = spectrogram(samples, SAMPLE_RATE)
    hop = WINDOW_SIZE // 2
    downsampled = -(-len(samples) // 4)  # ceil: a trailing partial block becomes one more sample
    expected_frames = (downsampled - WINDOW_SIZE) // hop + 1
    assert spec.shape == (expected_frames, WINDOW_SIZE // 2)


def test_short_audio_gives_no_peaks():
    assert extract_peaks(spectrogram(np.zeros(1000), SAMPLE_RATE), SAMPLE_RATE) == []


def test_peaks_use_valid_fft_bins():
    samples = make_song(3, seconds=5)
    peaks = extract_peaks(spectrogram(samples, SAMPLE_RATE), SAMPLE_RATE)
    assert peaks
    assert all(0 <= p.bin < WINDOW_SIZE // 2 for p in peaks)


def test_address_packs_bins_and_delta_without_overflow():
    # The highest bins (above ~5.1 kHz) used to overflow 9 bits and collide with low ones
    high, low = Peak(5500.0, 1.0, 511), Peak(10.0, 1.25, 1)
    address = create_address(high, low)
    assert address >> 23 == 511
    assert (address >> 14) & ((1 << MAX_FREQ_BITS) - 1) == 1
    assert address & ((1 << MAX_DELTA_BITS) - 1) == 250
    assert address < 2 ** 32
    assert create_address(high, low) != create_address(Peak(100.0, 1.0, 39), low)


def test_fingerprint_records_anchor_time_and_song():
    peaks = [Peak(100.0, 0.5, 9), Peak(200.0, 0.6, 18), Peak(300.0, 0.7, 28)]
    fps = fingerprint(peaks, song_id=7)
    assert len(fps) == 3
    assert {c.song_id for c in fps.values()} == {7}
    assert {c.anchor_time_ms for c in fps.values()} == {500, 600}


def test_clip_reproduces_the_songs_hashes():
    # A frame-aligned excerpt must produce the same addresses and time gaps as the full song,
    # whatever its length (peak times used to depend on the clip's duration)
    song = make_song(6, seconds=40)
    hop_in_samples = (WINDOW_SIZE // 2) * 4
    clip = song[100 * hop_in_samples:100 * hop_in_samples + 12 * SAMPLE_RATE]
    song_hashes = set(fingerprint(extract_peaks(spectrogram(song, SAMPLE_RATE), SAMPLE_RATE), 1))
    clip_hashes = set(fingerprint(extract_peaks(spectrogram(clip, SAMPLE_RATE), SAMPLE_RATE), 1))
    assert len(clip_hashes & song_hashes) / len(clip_hashes) > 0.9
