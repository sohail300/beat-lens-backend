"""WAV processing and audio conversion."""
import os
import subprocess
import json
import base64
import uuid
from typing import Dict, Optional
import soundfile as sf
import numpy as np
from app.config import FINGERPRINT_STEREO, MAX_CLIP_SECONDS, TMP_DIR, RECORDINGS_DIR
from app.models.schemas import Couple
from app.utils.helpers import create_folder, move_file, delete_file


class WavInfo:
    """WAV file information."""
    def __init__(self, channels: int, sample_rate: int, duration: float,
                 left_channel_samples: np.ndarray, right_channel_samples: Optional[np.ndarray] = None):
        self.channels = channels
        self.sample_rate = sample_rate
        self.duration = duration
        self.left_channel_samples = left_channel_samples
        self.right_channel_samples = right_channel_samples if right_channel_samples is not None else np.empty(0)


def convert_to_wav(input_file_path: str, max_seconds: Optional[float] = None) -> str:
    """
    Convert an input audio file to 16-bit 44.1kHz WAV, optionally keeping only the first max_seconds.
    The original file is deleted if it wasn't already a WAV.
    """
    if not os.path.exists(input_file_path):
        raise FileNotFoundError(f"Input file does not exist: {input_file_path}")

    channels = 2 if FINGERPRINT_STEREO else 1
    file_ext = os.path.splitext(input_file_path)[1].lower()

    output_file = os.path.splitext(input_file_path)[0] + ".wav"
    tmp_file = os.path.join(os.path.dirname(output_file), "tmp_" + os.path.basename(output_file))

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_file_path,
            *(["-t", str(max_seconds)] if max_seconds else []),
            "-c", "pcm_s16le",
            "-ar", "44100",
            "-ac", str(channels),
            tmp_file
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            last_line = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
            raise RuntimeError(f"Failed to convert to WAV: {last_line}")

        move_file(tmp_file, output_file)

        # Delete original if it wasn't WAV
        if file_ext != ".wav":
            delete_file(input_file_path)

        return output_file
    except Exception:
        delete_file(tmp_file)
        raise


def reformat_wav(input_file_path: str, channels: int) -> str:
    """Convert WAV file to specified number of channels."""
    if channels < 1 or channels > 2:
        channels = 1

    output_file = os.path.splitext(input_file_path)[0] + "rfm.wav"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_file_path,
        "-c", "pcm_s16le",
        "-ar", "44100",
        "-ac", str(channels),
        output_file
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("Failed to reformat WAV")

    return output_file


def read_wav_info(filename: str) -> WavInfo:
    """Read WAV file and return metadata and audio samples normalized to [-1, 1]."""
    data, sample_rate = sf.read(filename, dtype='int16', always_2d=True)

    data_float = data.astype(np.float64) / 32768.0

    channels = data.shape[1]
    duration = len(data) / sample_rate

    return WavInfo(
        channels=channels,
        sample_rate=sample_rate,
        duration=duration,
        left_channel_samples=data_float[:, 0],
        right_channel_samples=data_float[:, 1] if channels > 1 else None,
    )


def write_wav_file(filename: str, data: bytes, sample_rate: int, channels: int, bits_per_sample: int) -> None:
    """Write WAV file from raw audio data."""
    if sample_rate <= 0 or channels <= 0 or bits_per_sample <= 0:
        raise ValueError(f"Invalid parameters: sample_rate={sample_rate}, channels={channels}, bits_per_sample={bits_per_sample}")

    if bits_per_sample != 16:
        raise ValueError(f"Unsupported bits_per_sample: {bits_per_sample}")

    samples = np.frombuffer(data[:len(data) - len(data) % 2], dtype=np.int16)

    # Drop any incomplete trailing frame, then split into channels
    samples = samples[:len(samples) - len(samples) % channels].reshape(-1, channels)

    sf.write(filename, samples, sample_rate, subtype='PCM_16')


def get_metadata(file_path: str) -> dict:
    """Get metadata from file using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get metadata: {result.stderr}")

    metadata = json.loads(result.stdout)

    # Normalize tag keys to lowercase
    if "format" in metadata and "tags" in metadata["format"]:
        tags = metadata["format"]["tags"]
        metadata["format"]["tags"] = {k.lower(): v for k, v in tags.items()}

    if "streams" in metadata and len(metadata["streams"]) > 0:
        if "tags" in metadata["streams"][0]:
            tags = metadata["streams"][0]["tags"]
            metadata["streams"][0]["tags"] = {k.lower(): v for k, v in tags.items()}

    return metadata


def fingerprint_samples(samples: np.ndarray, sample_rate: int, song_id: int) -> Dict[int, Couple]:
    """Generate fingerprints for one channel of audio samples."""
    from app.core.spectrogram import spectrogram, extract_peaks
    from app.core.fingerprinting import fingerprint

    spectro = spectrogram(samples, sample_rate)
    peaks = extract_peaks(spectro, sample_rate)
    return fingerprint(peaks, song_id)


def fingerprint_audio(song_file_path: str, song_id: int) -> Dict[int, Couple]:
    """Generate fingerprint for audio file."""
    wav_file_path = convert_to_wav(song_file_path)
    wav_info = read_wav_info(wav_file_path)

    # Process left channel
    fingerprints = fingerprint_samples(wav_info.left_channel_samples, wav_info.sample_rate, song_id)

    # Process right channel if stereo
    if wav_info.channels == 2:
        fingerprints.update(fingerprint_samples(wav_info.right_channel_samples, wav_info.sample_rate, song_id))

    return fingerprints


def sample_fingerprint(file_path: str) -> Dict[int, int]:
    """
    Fingerprint a query sample (upload or recording) for matching.
    Converts the file to WAV, deletes it afterwards and returns {address: anchor_time_ms}.
    """
    wav_file_path = convert_to_wav(file_path, max_seconds=MAX_CLIP_SECONDS)
    try:
        wav_info = read_wav_info(wav_file_path)
        fingerprints = fingerprint_samples(wav_info.left_channel_samples, wav_info.sample_rate, 0)
    finally:
        delete_file(wav_file_path)

    return {address: couple.anchor_time_ms for address, couple in fingerprints.items()}


def process_recording(rec_data: dict, save_recording: bool = False) -> WavInfo:
    """Write a base64 PCM recording to disk, convert it to mono and return its samples."""
    decoded_audio_data = base64.b64decode(rec_data["audio"])

    create_folder(TMP_DIR)
    if save_recording:
        create_folder(RECORDINGS_DIR)

    file_name = f"{uuid.uuid4().hex}.wav"
    file_path = os.path.join(TMP_DIR, file_name)

    try:
        write_wav_file(
            file_path,
            decoded_audio_data,
            rec_data["sample_rate"],
            rec_data["channels"],
            rec_data["sample_size"]
        )

        reformatted_wav = reformat_wav(file_path, 1)
        wav_info = read_wav_info(reformatted_wav)

        if save_recording:
            move_file(reformatted_wav, os.path.join(RECORDINGS_DIR, file_name))
        else:
            delete_file(reformatted_wav)
    finally:
        delete_file(file_path)

    return wav_info
