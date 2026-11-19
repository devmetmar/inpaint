#!/home/opn/.local/share/mamba/envs/pyww3/bin/python
"""
Inpaint NaN values using iterative diffusion.

Similar to MATLAB's inpaint_nans by John D'Errico (method 4 - spring metaphor).
Uses scipy.ndimage for efficient filtering.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from scipy.ndimage import uniform_filter


def inpaint_nans_2d(data: np.ndarray, max_iter: int = 500, tol: float = 1e-5) -> np.ndarray:
    """
    Inpaint NaN values in a 2D array using iterative mean diffusion.

    This method replaces NaN values with the average of their neighbors,
    iterating until convergence. The result is a smooth interpolation
    similar to solving Laplace's equation.

    Args:
        data: 2D array with NaN values to fill
        max_iter: Maximum iterations (default 500)
        tol: Convergence tolerance (default 1e-5)

    Returns:
        Array with NaN values filled
    """
    if data.ndim != 2:
        raise ValueError(f"Expected 2D array, got {data.ndim}D")

    result = data.astype(np.float64).copy()
    mask = np.isnan(data)

    # No NaN to fill
    if not mask.any():
        return result.astype(np.float32)

    # All NaN - can't fill
    if mask.all():
        return result.astype(np.float32)

    # Initial fill with global mean of valid values
    valid_mean = np.nanmean(data)
    result[mask] = valid_mean

    # Iterative diffusion
    for i in range(max_iter):
        old = result.copy()

        # Apply mean filter (3x3 neighborhood)
        smoothed = uniform_filter(result, size=3, mode="nearest")

        # Only update NaN positions
        result[mask] = smoothed[mask]

        # Check convergence
        max_change = np.max(np.abs(result[mask] - old[mask]))
        if max_change < tol:
            break

    return result.astype(np.float32)


def inpaint_nans_3d(
    data: np.ndarray,
    max_iter: int = 500,
    tol: float = 1e-5,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    verbose: bool = True,
) -> np.ndarray:
    """
    Inpaint NaN values in a 3D array (lon, lat, time).

    Applies 2D inpainting to each time slice independently.

    Args:
        data: 3D array with shape (lon, lat, time)
        max_iter: Maximum iterations per slice
        tol: Convergence tolerance
        parallel: Use parallel processing (default True)
        max_workers: Number of workers for parallel (default: CPU count)
        verbose: Print progress (default True)

    Returns:
        Array with NaN values filled
    """
    import sys
    import time as time_module

    if data.ndim != 3:
        raise ValueError(f"Expected 3D array, got {data.ndim}D")

    nt = data.shape[2]
    nan_count = np.sum(np.isnan(data))

    # Skip if no NaN
    if nan_count == 0:
        if verbose:
            print("    No NaN values, skipping inpaint")
        return data.astype(np.float32)

    if verbose:
        print(f"    Inpainting {nt} timesteps ({nan_count:,} NaN values)...", end="", flush=True)

    start_time = time_module.perf_counter()
    result = np.zeros_like(data, dtype=np.float32)

    def process_slice(t: int) -> np.ndarray:
        return inpaint_nans_2d(data[:, :, t], max_iter=max_iter, tol=tol)

    if parallel and nt > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            slices = list(executor.map(process_slice, range(nt)))
        for t, s in enumerate(slices):
            result[:, :, t] = s
    else:
        for t in range(nt):
            result[:, :, t] = process_slice(t)
            if verbose and nt > 10 and (t + 1) % 20 == 0:
                print(f" {t+1}/{nt}", end="", flush=True)

    elapsed = time_module.perf_counter() - start_time
    if verbose:
        print(f" done ({elapsed:.1f}s)")

    return result


def test_inpaint():
    """Test inpainting with synthetic data."""
    print("Testing inpaint_nans_2d...")

    # Create test data with NaN hole
    ny, nx = 100, 150
    y, x = np.mgrid[0:ny, 0:nx]
    data = np.sin(x / 10) * np.cos(y / 10) + x / 50

    # Add NaN hole in center
    mask = ((x - nx // 2) ** 2 + (y - ny // 2) ** 2) < 400
    data_with_nan = data.copy()
    data_with_nan[mask] = np.nan

    print(f"  Input shape: {data_with_nan.shape}")
    print(f"  NaN count: {np.sum(np.isnan(data_with_nan))}")

    # Inpaint
    filled = inpaint_nans_2d(data_with_nan)

    print(f"  Output NaN count: {np.sum(np.isnan(filled))}")

    # Compare with original (should be close in filled region)
    rmse = np.sqrt(np.mean((filled[mask] - data[mask]) ** 2))
    print(f"  RMSE in filled region: {rmse:.6f}")

    # Test 3D
    print("\nTesting inpaint_nans_3d...")
    data_3d = np.stack([data_with_nan] * 10, axis=2)
    print(f"  Input shape: {data_3d.shape}")

    filled_3d = inpaint_nans_3d(data_3d)
    print(f"  Output NaN count: {np.sum(np.isnan(filled_3d))}")
    print("  OK!")


if __name__ == "__main__":
    test_inpaint()