"""Iterative mean-diffusion NaN inpainting.

Implements a spring / Laplace-style fill similar to John D'Errico's MATLAB
``inpaint_nans`` (method 4). Missing cells are repeatedly replaced by the
mean of their 3×3 neighborhood (:func:`scipy.ndimage.uniform_filter`) until
the maximum change falls below a tolerance or ``max_iter`` is reached.

Compared with Gaussian kernel interpolation, this method tends to produce
very smooth interiors that solve a discrete Laplace equation subject to
fixed valid-pixel boundary conditions.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
from scipy.ndimage import uniform_filter


def inpaint_nans_2d(data: np.ndarray, max_iter: int = 500, tol: float = 1e-5) -> np.ndarray:
    """Inpaint NaN values in a 2-D array using iterative mean diffusion.

    Algorithm:

    1. Identify the NaN mask (only those cells are ever updated).
    2. Seed missing cells with the global ``nanmean`` of the field.
    3. Each iteration applies a 3×3 uniform (mean) filter with
       ``mode="nearest"`` and copies the smoothed values back onto the
       masked cells only.
    4. Stop early when the max absolute change on masked cells is ``< tol``.

    The fixed valid pixels act as Dirichlet boundary conditions, so the
    filled region converges toward a discrete harmonic function.

    Parameters
    ----------
    data : numpy.ndarray
        Two-dimensional array with finite values and/or ``NaN``.
    max_iter : int, default 500
        Maximum diffusion iterations. Increase for very large holes if
        convergence is incomplete.
    tol : float, default 1e-5
        Convergence tolerance on the maximum absolute update within the
        NaN mask. Smaller values yield a smoother / more fully converged
        solution at higher cost.

    Returns
    -------
    numpy.ndarray
        Filled array with dtype ``float32`` and the same shape as ``data``.
        If the input has no NaNs, or is entirely NaN, the array is returned
        as ``float32`` without iterative updates.

    Raises
    ------
    ValueError
        If ``data`` is not 2-dimensional.

    Notes
    -----
    * Only originally-NaN locations are modified after the seed step;
      observed values remain exactly as in the input.
    * Entirely NaN arrays cannot be filled (no boundary information).

    Examples
    --------
    >>> import numpy as np
    >>> from inpaint import inpaint_nans_2d
    >>> a = np.arange(25, dtype=float).reshape(5, 5)
    >>> a[2, 2] = np.nan
    >>> out = inpaint_nans_2d(a, max_iter=100)
    >>> np.isnan(out).any()
    False

    See Also
    --------
    inpaint_nans_nd : Apply this routine over leading dimensions.
    inpaint_nans_3d : Convenience wrapper for 3-D arrays.
    inpaint.iterative_diffusion : xarray Dataset / DataArray wrapper.
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
    """Inpaint NaNs on the last two axes; process leading dims independently.

    Reshapes ``data`` of shape ``(..., y, x)`` into a flat list of 2-D
    slices and calls :func:`inpaint_nans_2d` on each. Optional thread-pool
    parallelism speeds up long ``time`` / ``depth`` axes.

    Parameters
    ----------
    data : numpy.ndarray
        Array with shape ``(..., y, x)`` and at least two dimensions.
    max_iter : int, default 500
        Maximum iterations per spatial slice (see :func:`inpaint_nans_2d`).
    tol : float, default 1e-5
        Convergence tolerance per slice.
    parallel : bool, default True
        Use a thread pool when more than one leading slice is present.
    max_workers : int or None, default None
        Thread pool size; ``None`` uses the executor default.
    verbose : bool, default False
        Print progress (slice count, NaN count, elapsed seconds).

    Returns
    -------
    numpy.ndarray
        Filled array with dtype ``float32`` and the same shape as ``data``.

    Raises
    ------
    ValueError
        If ``data`` has fewer than two dimensions.

    Examples
    --------
    >>> import numpy as np
    >>> from inpaint import inpaint_nans_nd
    >>> vol = np.ones((4, 10, 10))
    >>> vol[:, 4, 4] = np.nan
    >>> out = inpaint_nans_nd(vol, max_iter=50, parallel=False)
    >>> np.isnan(out).any()
    False

    See Also
    --------
    inpaint_nans_2d : Underlying 2-D solver.
    inpaint_nans_3d : Thin wrapper requiring exactly 3-D input.
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
    """Inpaint NaN values in a 3-D array with spatial axes last.

    Convenience wrapper around :func:`inpaint_nans_nd` that requires
    ``data.ndim == 3``. Typical layouts after transpose include
    ``(time, y, x)`` or ``(lon, lat, time)`` as long as the last two axes
    form the spatial plane that should be filled.

    For 4-D+ fields (e.g. ``time, depth, lat, lon``) call
    :func:`inpaint_nans_nd` directly, or use the xarray API which detects
    spatial dimension names.

    Parameters
    ----------
    data : numpy.ndarray
        Exactly 3-dimensional array; last two axes are treated as ``(y, x)``.
    max_iter : int, default 500
        Maximum iterations per slice.
    tol : float, default 1e-5
        Convergence tolerance per slice.
    parallel : bool, default True
        Parallelize across the leading axis when length > 1.
    max_workers : int or None, default None
        Thread pool size.
    verbose : bool, default True
        Print progress (default ``True`` for historical CLI-style use).

    Returns
    -------
    numpy.ndarray
        Filled ``float32`` array with the same shape as ``data``.

    Raises
    ------
    ValueError
        If ``data.ndim != 3``.

    See Also
    --------
    inpaint_nans_nd : Preferred entry point for arbitrary leading dims.
    inpaint_nans_2d : Single-slice solver.
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


def test_iterative_diffusion():
    """Run a synthetic self-check for the iterative diffusion methodology.

    Creates a smooth analytic field, inserts a circular NaN hole, fills with
    :func:`inpaint_nans_2d` and :func:`inpaint_nans_3d`, reports RMSE inside
    the hole, and raises if any NaNs remain.

    Returns
    -------
    None
        Prints diagnostics to stdout for interactive or CI smoke checks.

    Raises
    ------
    AssertionError
        If 2-D or 3-D filled results still contain NaN values.

    Examples
    --------
    >>> from inpaint import test_iterative_diffusion  # doctest: +SKIP
    >>> test_iterative_diffusion()  # doctest: +SKIP

    See Also
    --------
    test_inpaint : Backward-compatible alias for this function.
    """
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
    if np.isnan(filled).any():
        raise AssertionError("iterative diffusion left NaN values")

    rmse = np.sqrt(np.mean((filled[mask] - data[mask]) ** 2))
    print(f"  RMSE in filled region: {rmse:.6f}")

    print("\nTesting inpaint_nans_3d...")
    data_3d = np.stack([data_with_nan] * 10, axis=0)
    print(f"  Input shape: {data_3d.shape}")

    filled_3d = inpaint_nans_3d(data_3d, verbose=False)
    print(f"  Output NaN count: {np.sum(np.isnan(filled_3d))}")
    if np.isnan(filled_3d).any():
        raise AssertionError("iterative diffusion 3d left NaN values")
    print("  OK!")


# Backward-compatible alias
test_inpaint = test_iterative_diffusion


if __name__ == "__main__":
    test_iterative_diffusion()
