"""Fast Fourier Transform implementation."""
import numpy as np
from typing import List


def fft(input_data: List[float]) -> np.ndarray:
    """
    Compute the Fast Fourier Transform (FFT) of the input data.
    Converts signal from time domain to frequency domain.
    """
    complex_array = np.array(input_data, dtype=complex)
    return recursive_fft(complex_array)


def recursive_fft(complex_array: np.ndarray) -> np.ndarray:
    """Recursive FFT implementation."""
    N = len(complex_array)
    if N <= 1:
        return complex_array
    
    # Split into even and odd indices
    even = recursive_fft(complex_array[::2])
    odd = recursive_fft(complex_array[1::2])
    
    # Combine results
    fft_result = np.zeros(N, dtype=complex)
    for k in range(N // 2):
        t = np.exp(-2j * np.pi * k / N) * odd[k]
        fft_result[k] = even[k] + t
        fft_result[k + N // 2] = even[k] - t
    
    return fft_result

