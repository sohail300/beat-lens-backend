"""WAV processing and audio conversion."""
import os
import subprocess
import json
import base64
from typing import Optional, Tuple
import soundfile as sf
import numpy as np
from app.config import FINGERPRINT_STEREO, TMP_DIR, RECORDINGS_DIR
from app.utils.helpers import create_folder, move_file, delete_file
from app.utils.logger import logger


class WavInfo:
    """WAV file information."""
    def __init__(self, channels: int, sample_rate: int, duration: float,
                 data: bytes, left_channel_samples: list, right_channel_samples: Optional[list] = None):
        self.channels = channels
        self.sample_rate = sample_rate
        self.duration = duration
        self.data = data
        self.left_channel_samples = left_channel_samples
        self.right_channel_samples = right_channel_samples or []


def convert_to_wav(input_file_path: str) -> str:
    """Convert an input audio file to WAV format."""
    if not os.path.exists(input_file_path):
        raise FileNotFoundError(f"Input file does not exist: {input_file_path}")
    
    channels = 2 if FINGERPRINT_STEREO else 1
    file_ext = os.path.splitext(input_file_path)[1]
    
    output_file = os.path.splitext(input_file_path)[0] + ".wav"
    tmp_file = os.path.join(os.path.dirname(output_file), "tmp_" + os.path.basename(output_file))
    
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_file_path,
            "-c", "pcm_s16le",
            "-ar", "44100",
            "-ac", str(channels),
            tmp_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to convert to WAV: {result.stderr}")
        
        move_file(tmp_file, output_file)
        
        # Delete original if it wasn't WAV
        if file_ext != ".wav":
            delete_file(input_file_path)
        
        return output_file
    except Exception as e:
        if os.path.exists(tmp_file):
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
        raise RuntimeError(f"Failed to reformat WAV: {result.stderr}")
    
    return output_file


def read_wav_info(filename: str) -> WavInfo:
    """Read WAV file and return metadata and audio samples."""
    data, sample_rate = sf.read(filename, dtype='int16')
    
    # Convert to float64 normalized to [-1, 1]
    data_float = data.astype(np.float64) / 32768.0
    
    channels = 1 if len(data.shape) == 1 else data.shape[1]
    duration = len(data) / sample_rate
    
    # Read raw bytes for data
    with open(filename, 'rb') as f:
        wav_bytes = f.read()
        # Skip WAV header (typically 44 bytes)
        data_bytes = wav_bytes[44:]
    
    if channels == 1:
        left_channel_samples = data_float.tolist()
        right_channel_samples = []
    else:
        left_channel_samples = data_float[:, 0].tolist()
        right_channel_samples = data_float[:, 1].tolist()
    
    return WavInfo(
        channels=channels,
        sample_rate=sample_rate,
        duration=duration,
        data=data_bytes,
        left_channel_samples=left_channel_samples,
        right_channel_samples=right_channel_samples
    )


def write_wav_file(filename: str, data: bytes, sample_rate: int, channels: int, bits_per_sample: int) -> None:
    """Write WAV file from raw audio data."""
    if sample_rate <= 0 or channels <= 0 or bits_per_sample <= 0:
        raise ValueError(f"Invalid parameters: sample_rate={sample_rate}, channels={channels}, bits_per_sample={bits_per_sample}")
    
    # Convert bytes to numpy array
    if bits_per_sample == 16:
        samples = np.frombuffer(data, dtype=np.int16)
        # Normalize to float
        samples_float = samples.astype(np.float64) / 32768.0
    else:
        raise ValueError(f"Unsupported bits_per_sample: {bits_per_sample}")
    
    # Reshape if stereo
    if channels == 2:
        if len(samples_float) % 2 != 0:
            samples_float = samples_float[:-1]
        samples_float = samples_float.reshape(-1, 2)
    else:
        samples_float = samples_float.reshape(-1, 1)
    
    # Write using soundfile
    sf.write(filename, samples_float, sample_rate, subtype='PCM_16')


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
        normalized_tags = {k.lower(): v for k, v in tags.items()}
        metadata["format"]["tags"] = normalized_tags
    
    if "streams" in metadata and len(metadata["streams"]) > 0:
        if "tags" in metadata["streams"][0]:
            tags = metadata["streams"][0]["tags"]
            normalized_tags = {k.lower(): v for k, v in tags.items()}
            metadata["streams"][0]["tags"] = normalized_tags
    
    return metadata


def fingerprint_audio(song_file_path: str, song_id: int) -> dict:
    """Generate fingerprint for audio file."""
    from app.core.spectrogram import spectrogram, extract_peaks
    from app.core.fingerprinting import fingerprint
    from app.utils.helpers import extend_map
    
    wav_file_path = convert_to_wav(song_file_path)
    wav_info = read_wav_info(wav_file_path)
    
    fingerprints = {}
    
    # Process left channel
    spectro = spectrogram(wav_info.left_channel_samples, wav_info.sample_rate)
    peaks = extract_peaks(spectro, wav_info.duration, wav_info.sample_rate)
    extend_map(fingerprints, fingerprint(peaks, song_id))
    
    # Process right channel if stereo
    if wav_info.channels == 2:
        spectro = spectrogram(wav_info.right_channel_samples, wav_info.sample_rate)
        peaks = extract_peaks(spectro, wav_info.duration, wav_info.sample_rate)
        extend_map(fingerprints, fingerprint(peaks, song_id))
    
    return fingerprints


def process_recording(rec_data: dict, save_recording: bool = False) -> list:
    """Process recording data and return audio samples."""
    decoded_audio_data = base64.b64decode(rec_data["audio"])
    
    create_folder(TMP_DIR)
    if save_recording:
        create_folder(RECORDINGS_DIR)
    
    from datetime import datetime
    now = datetime.now()
    file_name = f"{now.second:04d}_{now.minute:02d}_{now.hour:02d}_{now.day:02d}_{now.month:02d}_{now.year:04d}.wav"
    file_path = os.path.join(TMP_DIR, file_name)
    
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
        new_file_path = os.path.join(RECORDINGS_DIR, file_name)
        move_file(reformatted_wav, new_file_path)
    else:
        delete_file(reformatted_wav)
    
    delete_file(file_path)
    
    return wav_info.left_channel_samples

