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

    if not mask.any():
        return result.astype(np.float32)

    if mask.all():
        return result.astype(np.float32)

    valid_mean = np.nanmean(data)
    result[mask] = valid_mean

    for _ in range(max_iter):
        old = result.copy()
        smoothed = uniform_filter(result, size=3, mode="nearest")
        result[mask] = smoothed[mask]
        max_change = np.max(np.abs(result[mask] - old[mask]))
        if max_change < tol:
            break

    return result.astype(np.float32)


def inpaint_nans_nd(
    data: np.ndarray,
    max_iter: int = 500,
    tol: float = 1e-5,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    verbose: bool = False,
) -> np.ndarray:
    """
    Inpaint NaNs on the last two axes (spatial); leading dims sliced independently.

    Args:
        data: N-D array with shape (..., y, x)
        max_iter: Maximum iterations per slice
        tol: Convergence tolerance
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
        return inpaint_nans_2d(data, max_iter=max_iter, tol=tol)

    leading = data.shape[:-2]
    n_slices = int(np.prod(leading)) if leading else 1
    flat = data.reshape((n_slices, data.shape[-2], data.shape[-1]))

    nan_count = int(np.isnan(flat).sum())
    if nan_count == 0:
        if verbose:
            print("    No NaN values, skipping inpaint")
        return data.astype(np.float32)

    if verbose:
        print(
            f"    Inpainting {n_slices} slices ({nan_count:,} NaN values)...",
            end="",
            flush=True,
        )

    start_time = time_module.perf_counter()
    result = np.empty_like(flat, dtype=np.float32)

    def process_slice(i: int) -> np.ndarray:
        return inpaint_nans_2d(flat[i], max_iter=max_iter, tol=tol)

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
        print(f" done ({time_module.perf_counter() - start_time:.1f}s)")

    return result.reshape(data.shape)


def inpaint_nans_3d(
    data: np.ndarray,
    max_iter: int = 500,
    tol: float = 1e-5,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    verbose: bool = True,
) -> np.ndarray:
    """
    Inpaint NaN values in a 3D array (..., y, x) — typically (lon, lat, time)
    after transpose, or any 3D with spatial axes last.

    Prefer :func:`inpaint_nans_nd` for arbitrary leading dimensions.
    """
    if data.ndim != 3:
        raise ValueError(f"Expected 3D array, got {data.ndim}D")
    return inpaint_nans_nd(
        data,
        max_iter=max_iter,
        tol=tol,
        parallel=parallel,
        max_workers=max_workers,
        verbose=verbose,
    )


def test_inpaint():
    """Test inpainting with synthetic data."""
    print("Testing inpaint_nans_2d...")

    ny, nx = 100, 150
    y, x = np.mgrid[0:ny, 0:nx]
    data = np.sin(x / 10) * np.cos(y / 10) + x / 50

    mask = ((x - nx // 2) ** 2 + (y - ny // 2) ** 2) < 400
    data_with_nan = data.copy()
    data_with_nan[mask] = np.nan

    print(f"  Input shape: {data_with_nan.shape}")
    print(f"  NaN count: {np.sum(np.isnan(data_with_nan))}")

    filled = inpaint_nans_2d(data_with_nan)

    print(f"  Output NaN count: {np.sum(np.isnan(filled))}")

    rmse = np.sqrt(np.mean((filled[mask] - data[mask]) ** 2))
    print(f"  RMSE in filled region: {rmse:.6f}")

    print("\nTesting inpaint_nans_3d...")
    data_3d = np.stack([data_with_nan] * 10, axis=0)
    print(f"  Input shape: {data_3d.shape}")

    filled_3d = inpaint_nans_3d(data_3d, verbose=False)
    print(f"  Output NaN count: {np.sum(np.isnan(filled_3d))}")
    print("  OK!")


if __name__ == "__main__":
    test_inpaint()
