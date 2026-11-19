"""
Gaussian kernel NaN fill using Astropy convolution.

Based on interpolate_replace_nans + Gaussian2DKernel (see ipynb/gaussian_kernel_smoothing.ipynb).
Large contiguous NaN holes are filled with multiple passes; the kernel grows if a pass stalls.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import warnings

import numpy as np
from astropy.convolution import Gaussian2DKernel, interpolate_replace_nans


def gaussian_fill_2d(
    data: np.ndarray,
    stddev: float = 1.0,
    max_passes: int = 64,
) -> np.ndarray:
    """
    Fill NaN values in a 2D array with Gaussian kernel interpolation.

    Args:
        data: 2D array with NaN values to fill
        stddev: Initial Gaussian kernel standard deviation (x_stddev)
        max_passes: Maximum convolution passes (grows kernel if a pass makes no progress)

    Returns:
        Array with NaN values filled (float32). Remaining NaNs only if the
        entire array is NaN or max_passes is exhausted.
    """
    if data.ndim != 2:
        raise ValueError(f"Expected 2D array, got {data.ndim}D")

    if not np.isnan(data).any():
        return data.astype(np.float32)

    if np.isnan(data).all():
        return data.astype(np.float32)

    filled = data.astype(np.float64).copy()
    current_std = float(stddev)

    for _ in range(max_passes):
        if not np.isnan(filled).any():
            break
        before = int(np.isnan(filled).sum())
        kernel = Gaussian2DKernel(x_stddev=current_std)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=".*nan_treatment.*",
                module="astropy.convolution.convolve",
            )
            nxt = interpolate_replace_nans(filled, kernel)
        filled = np.asarray(nxt, dtype=np.float64)
        after = int(np.isnan(filled).sum())
        if after == 0:
            break
        if after >= before:
            current_std *= 1.5

    return filled.astype(np.float32)


def gaussian_fill_nd(
    data: np.ndarray,
    stddev: float = 1.0,
    max_passes: int = 64,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    verbose: bool = False,
) -> np.ndarray:
    """
    Fill NaNs with Gaussian interpolation on the last two axes (spatial).

    Extra leading dimensions (e.g. time, depth) are processed slice-by-slice.

    Args:
        data: N-D array with shape (..., y, x)
        stddev: Gaussian kernel standard deviation
        max_passes: Max passes per slice (see :func:`gaussian_fill_2d`)
        parallel: Use thread pool when there are multiple slices
        max_workers: Thread pool size (default: CPU count)
        verbose: Print progress

    Returns:
        Array with NaN values filled (float32)
    """
    import time as time_module

    if data.ndim < 2:
        raise ValueError(f"Expected at least 2D array, got {data.ndim}D")

    if data.ndim == 2:
        return gaussian_fill_2d(data, stddev=stddev, max_passes=max_passes)

    leading = data.shape[:-2]
    n_slices = int(np.prod(leading)) if leading else 1
    flat = data.reshape((n_slices, data.shape[-2], data.shape[-1]))

    nan_count = int(np.isnan(flat).sum())
    if nan_count == 0:
        if verbose:
            print("    No NaN values, skipping gaussian fill")
        return data.astype(np.float32)

    if verbose:
        print(
            f"    Gaussian fill {n_slices} slices ({nan_count:,} NaN values)...",
            end="",
            flush=True,
        )

    start = time_module.perf_counter()
    result = np.empty_like(flat, dtype=np.float32)

    def process_slice(i: int) -> np.ndarray:
        return gaussian_fill_2d(flat[i], stddev=stddev, max_passes=max_passes)

    if parallel and n_slices > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            slices = list(executor.map(process_slice, range(n_slices)))
        for i, s in enumerate(slices):
            result[i] = s
    else:
        for i in range(n_slices):
            result[i] = process_slice(i)
            if verbose and n_slices > 10 and (i + 1) % 20 == 0:
                print(f" {i + 1}/{n_slices}", end="", flush=True)

    if verbose:
        print(f" done ({time_module.perf_counter() - start:.1f}s)")

    return result.reshape(data.shape)
