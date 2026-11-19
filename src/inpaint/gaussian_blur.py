"""Gaussian kernel NaN fill using Astropy convolution.

Implements coastal / gap filling via
:func:`astropy.convolution.interpolate_replace_nans` and
:class:`astropy.convolution.Gaussian2DKernel`.

Large contiguous NaN regions that exceed the initial kernel footprint are
handled with multiple passes; if a pass does not reduce the NaN count, the
kernel standard deviation is grown by 1.5× and filling continues until the
array is complete or ``max_passes`` is reached.

See also ``ipynb/gaussian_kernel_smoothing.ipynb`` for the original notebook
pipeline that motivated this module.
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
    """Fill NaN values in a 2-D array with Gaussian kernel interpolation.

    Each pass builds a :class:`~astropy.convolution.Gaussian2DKernel` with the
    current ``stddev`` and replaces NaNs by a weighted local average of valid
    neighbors. Valid (non-NaN) pixels are left unchanged by the interpolator;
    only missing cells are updated.

    If the NaN hole is larger than the kernel support, a single pass cannot
    fill the interior. This function therefore loops up to ``max_passes``
    times. When a pass fails to reduce the NaN count, ``stddev`` is multiplied
    by ``1.5`` so the next kernel is wider.

    Parameters
    ----------
    data : numpy.ndarray
        Two-dimensional array containing finite values and/or ``NaN``.
        Any numeric dtype is accepted; computation uses ``float64``.
    stddev : float, default 1.0
        Initial Gaussian kernel standard deviation (Astropy ``x_stddev``).
        Smaller values preserve local structure; larger values smooth more
        aggressively and fill wider gaps per pass.
    max_passes : int, default 64
        Maximum number of convolution / interpolate passes. Also caps how
        many times the kernel may grow when progress stalls.

    Returns
    -------
    numpy.ndarray
        Filled array with dtype ``float32`` and the same shape as ``data``.
        Remaining NaNs occur only if the entire input is NaN, or if
        ``max_passes`` is exhausted before the hole is closed.

    Raises
    ------
    ValueError
        If ``data`` is not 2-dimensional.

    Notes
    -----
    * No-op (cast to ``float32``) when there are no NaNs.
    * All-NaN inputs are returned unchanged (cast to ``float32``); there is
      no valid neighborhood to extrapolate from.
    * Astropy warnings about NaNs larger than the kernel are suppressed
      because multi-pass growth is the intended remedy.

    Examples
    --------
    >>> import numpy as np
    >>> from inpaint import gaussian_fill_2d
    >>> a = np.ones((5, 5))
    >>> a[2, 2] = np.nan
    >>> out = gaussian_fill_2d(a, stddev=1.0)
    >>> np.isnan(out).any()
    False

    See Also
    --------
    gaussian_fill_nd : Same algorithm over leading non-spatial axes.
    inpaint.gaussian_blur : xarray Dataset / DataArray wrapper.
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
    """Fill NaNs with Gaussian interpolation on the last two axes (spatial).

    Leading dimensions (for example ``time``, ``depth``, or ensemble members)
    are treated as independent 2-D slices. Each slice is passed to
    :func:`gaussian_fill_2d`. When ``parallel`` is true and more than one
    slice exists, slices are processed with a :class:`~concurrent.futures.ThreadPoolExecutor`.

    Parameters
    ----------
    data : numpy.ndarray
        Array of shape ``(..., y, x)`` with at least two dimensions. The last
        two axes are the spatial plane.
    stddev : float, default 1.0
        Initial Gaussian kernel standard deviation forwarded to
        :func:`gaussian_fill_2d`.
    max_passes : int, default 64
        Maximum interpolate passes per spatial slice.
    parallel : bool, default True
        If ``True`` and there is more than one leading slice, run slices in
        a thread pool. Set ``False`` for deterministic single-threaded runs
        or when nested parallelism is undesirable.
    max_workers : int or None, default None
        Thread pool size. ``None`` lets the executor choose (typically the
        number of CPUs).
    verbose : bool, default False
        If ``True``, print slice counts, NaN totals, and elapsed time.

    Returns
    -------
    numpy.ndarray
        Filled array with dtype ``float32`` and the same shape as ``data``.

    Raises
    ------
    ValueError
        If ``data`` has fewer than two dimensions.

    Notes
    -----
    For a plain 2-D input this function delegates directly to
    :func:`gaussian_fill_2d` (no thread pool).

    Examples
    --------
    >>> import numpy as np
    >>> from inpaint import gaussian_fill_nd
    >>> vol = np.ones((3, 8, 8))
    >>> vol[:, 3:5, 3:5] = np.nan
    >>> out = gaussian_fill_nd(vol, stddev=1.0, parallel=False)
    >>> out.shape
    (3, 8, 8)
    >>> np.isnan(out).any()
    False

    See Also
    --------
    gaussian_fill_2d : Per-slice 2-D implementation.
    inpaint.gaussian_blur : xarray-facing API.
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


def test_gaussian_blur():
    """Run a synthetic self-check for the Gaussian fill methodology.

    Builds a smooth analytic 2-D field, punches a circular NaN hole, fills
    with :func:`gaussian_fill_2d` and :func:`gaussian_fill_nd`, prints RMSE
    in the hole, and raises :class:`AssertionError` if any NaNs remain.

    Returns
    -------
    None
        Prints progress to stdout. Intended for interactive use
        (``from inpaint import test_gaussian_blur; test_gaussian_blur()``)
        or as a smoke check from pytest.

    Raises
    ------
    AssertionError
        If the filled 2-D or N-D result still contains NaN values.

    Examples
    --------
    >>> from inpaint import test_gaussian_blur  # doctest: +SKIP
    >>> test_gaussian_blur()  # doctest: +SKIP
    """
    print("Testing gaussian_fill_2d...")

    ny, nx = 100, 150
    y, x = np.mgrid[0:ny, 0:nx]
    data = np.sin(x / 10) * np.cos(y / 10) + x / 50

    mask = ((x - nx // 2) ** 2 + (y - ny // 2) ** 2) < 400
    data_with_nan = data.copy()
    data_with_nan[mask] = np.nan

    print(f"  Input shape: {data_with_nan.shape}")
    print(f"  NaN count: {np.sum(np.isnan(data_with_nan))}")

    filled = gaussian_fill_2d(data_with_nan, stddev=1.0)

    print(f"  Output NaN count: {np.sum(np.isnan(filled))}")
    if np.isnan(filled).any():
        raise AssertionError("gaussian fill left NaN values")

    rmse = np.sqrt(np.mean((filled[mask] - data[mask]) ** 2))
    print(f"  RMSE in filled region: {rmse:.6f}")

    print("\nTesting gaussian_fill_nd...")
    data_3d = np.stack([data_with_nan] * 5, axis=0)
    print(f"  Input shape: {data_3d.shape}")

    filled_3d = gaussian_fill_nd(data_3d, stddev=1.0, parallel=False, verbose=False)
    print(f"  Output NaN count: {np.sum(np.isnan(filled_3d))}")
    if np.isnan(filled_3d).any():
        raise AssertionError("gaussian fill nd left NaN values")
    print("  OK!")


if __name__ == "__main__":
    test_gaussian_blur()
