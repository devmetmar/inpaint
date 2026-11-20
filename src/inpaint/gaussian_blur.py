"""Gaussian kernel NaN fill (small-kernel SciPy convolve).

Fills missing cells with a local Gaussian-weighted average of valid
neighbors. Valid (non-NaN) pixels are never modified.

Uses an explicit small 2-D Gaussian kernel with
:func:`scipy.ndimage.convolve` (much cheaper / less RAM than
``gaussian_filter`` on large coastal grids). Multi-pass with capped
sigma growth closes wider holes.

This module is the reproducible engine behind
``inpaint.fill_nans(..., method="gaussian")``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import os

import numpy as np
from scipy.ndimage import convolve

_GAUSSIAN_TRUNCATE = 2.0
_MAX_SIGMA = 6.0


def _limit_blas_threads() -> None:
    for key in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(key, "1")


def _gaussian_kernel2d(sigma: float, truncate: float = _GAUSSIAN_TRUNCATE) -> np.ndarray:
    radius = max(1, int(truncate * float(sigma) + 0.5))
    y, x = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    k = np.exp(-(x * x + y * y) / (2.0 * sigma * sigma))
    k /= k.sum()
    return k.astype(np.float64)


def gaussian_fill_2d(
    data: np.ndarray,
    stddev: float = 1.0,
    max_passes: int = 64,
) -> np.ndarray:
    """Fill NaN values in a 2-D array with Gaussian-weighted interpolation."""
    if data.ndim != 2:
        raise ValueError(f"Expected 2D array, got {data.ndim}D")

    if not np.isnan(data).any():
        return data.astype(np.float32)

    if np.isnan(data).all():
        return data.astype(np.float32)

    out = np.asarray(data, dtype=np.float64, order="C").copy()
    current_std = float(stddev)

    for _ in range(int(max_passes)):
        nan = np.isnan(out)
        if not nan.any():
            break
        before = int(nan.sum())
        valid = (~nan).astype(np.float64)
        vals = out.copy()
        vals[nan] = 0.0
        kernel = _gaussian_kernel2d(current_std)
        num = convolve(vals, kernel, mode="nearest")
        den = convolve(valid, kernel, mode="nearest")
        can_fill = nan & (den > 1e-12)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[can_fill] = (num / np.maximum(den, 1e-12))[can_fill]
        after = int(np.isnan(out).sum())
        if after == 0:
            break
        if after >= before:
            current_std = min(current_std * 1.5, _MAX_SIGMA)

    return out.astype(np.float32)


def gaussian_fill_nd(
    data: np.ndarray,
    stddev: float = 1.0,
    max_passes: int = 64,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    verbose: bool = False,
) -> np.ndarray:
    """Fill NaNs with Gaussian interpolation on the last two axes (spatial)."""
    import time as time_module

    if data.ndim < 2:
        raise ValueError(f"Expected at least 2D array, got {data.ndim}D")

    if data.ndim == 2:
        return gaussian_fill_2d(data, stddev=stddev, max_passes=max_passes)

    leading = data.shape[:-2]
    n_slices = int(np.prod(leading)) if leading else 1
    flat = np.ascontiguousarray(
        np.asarray(data).reshape((n_slices, data.shape[-2], data.shape[-1]))
    )

    if not np.isnan(flat).any():
        if verbose:
            print("    No NaN values, skipping gaussian fill")
        return data.astype(np.float32)

    nan_count = int(np.isnan(flat).sum())
    if verbose:
        print(
            f"    Gaussian fill {n_slices} slices ({nan_count:,} NaN values)...",
            end="",
            flush=True,
        )

    start = time_module.perf_counter()
    result = np.empty_like(flat, dtype=np.float32)
    _limit_blas_threads()

    def process_slice(i: int) -> np.ndarray:
        _limit_blas_threads()
        return gaussian_fill_2d(flat[i], stddev=stddev, max_passes=max_passes)

    workers = max_workers
    if workers is None:
        workers = min(32, os.cpu_count() or 1)

    if parallel and n_slices > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for i, s in enumerate(executor.map(process_slice, range(n_slices))):
                result[i] = s
    else:
        for i in range(n_slices):
            result[i] = process_slice(i)
            if verbose and n_slices > 10 and (i + 1) % 20 == 0:
                print(f" {i + 1}/{n_slices}", end="", flush=True)

    if verbose:
        print(f" done ({time_module.perf_counter() - start:.1f}s)")

    return result.reshape(data.shape)


def test_gaussian_blur():
    """Synthetic self-check for the Gaussian fill methodology."""
    print("Testing gaussian_fill_2d...")

    ny, nx = 100, 150
    y, x = np.mgrid[0:ny, 0:nx]
    data = np.sin(x / 10) * np.cos(y / 10) + x / 50

    mask = ((x - nx // 2) ** 2 + (y - ny // 2) ** 2) < 400
    data_with_nan = data.copy()
    data_with_nan[mask] = np.nan

    filled = gaussian_fill_2d(data_with_nan, stddev=1.0)
    if np.isnan(filled).any():
        raise AssertionError("gaussian fill left NaN values")

    print("\nTesting gaussian_fill_nd...")
    data_3d = np.stack([data_with_nan] * 5, axis=0)
    filled_3d = gaussian_fill_nd(data_3d, stddev=1.0, parallel=False, verbose=False)
    if np.isnan(filled_3d).any():
        raise AssertionError("gaussian fill nd left NaN values")
    print("  OK!")


if __name__ == "__main__":
    test_gaussian_blur()
