"""Fast Fourier Transform."""
import numpy as np


def fft(input_data: np.ndarray) -> np.ndarray:
    """
    Compute the Fast Fourier Transform (FFT) of the input data.
    Converts signal from time domain to frequency domain.
    Accepts a 1-D frame, or a 2-D array of frames (one FFT per row).
    """
    return np.fft.fft(np.asarray(input_data, dtype=np.float64), axis=-1)
