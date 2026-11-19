"""xarray-facing API: accept Dataset/DataArray, return the same type.

This module is the primary public entry point for coastal NaN filling.
It detects spatial (and time) dimensions via CF/NetCDF Conventions
metadata on coordinates, applies a chosen numpy algorithm on each
spatial plane, and reconstructs an ``xarray`` object that preserves
dimension order, coordinates, name, and attributes.

Dimension detection (see :mod:`inpaint.dims`) prefers, in order:

1. Coordinate ``standard_name`` (e.g. ``latitude``, ``longitude``, ``time``)
2. Coordinate ``axis`` (``Y`` / ``X`` / ``T`` / ``Z``)
3. Coordinate ``units`` (``degrees_north``, ``degrees_east``, ``… since …``)
4. Common dimension *names* as a last-resort fallback
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Union

import numpy as np
import xarray as xr

from .dims import find_spatial_dims, find_time_dim, non_spatial_dims
from .gaussian_blur import gaussian_fill_nd
from .iterative_diffusion import inpaint_nans_nd

ArrayLike = Union[xr.DataArray, xr.Dataset]


def _numeric_data_vars(ds: xr.Dataset) -> List[str]:
    """Return names of numeric data variables in a Dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        Input dataset.

    Returns
    -------
    list of str
        ``data_vars`` whose dtype is a NumPy number subtype. Non-numeric
        or exotic dtypes that raise in ``np.issubdtype`` are skipped.
    """
    names: List[str] = []
    for name, da in ds.data_vars.items():
        try:
            if np.issubdtype(da.dtype, np.number):
                names.append(name)
        except TypeError:
            continue
    return names


def _apply_nd_to_dataarray(
    da: xr.DataArray,
    nd_func,
    **kwargs,
) -> xr.DataArray:
    """Apply an ``(..., y, x)`` numpy fill function to one DataArray.

    Resolves spatial dims via CF metadata (:func:`inpaint.dims.find_spatial_dims`),
    treats time/vertical/other dims as leading slices
    (:func:`inpaint.dims.non_spatial_dims`), transposes so spatial axes are
    last, runs ``nd_func``, then restores the original dimension order and
    non-dimensional coordinates.

    Parameters
    ----------
    da : xarray.DataArray
        Input field with at least two dimensions and detectable Y/X axes.
    nd_func : callable
        Function with signature ``nd_func(ndarray, **kwargs) -> ndarray``
        that fills NaNs on the last two axes (e.g. ``gaussian_fill_nd`` or
        ``inpaint_nans_nd``).
    **kwargs
        Forwarded unchanged to ``nd_func``.

    Returns
    -------
    xarray.DataArray
        Filled array with the same dims, name, and attrs as ``da``.
        Dimensional and non-dimensional coordinates are preserved.

    Raises
    ------
    ValueError
        If ``da`` has fewer than two dimensions, or spatial dims cannot
        be detected from CF attributes / names.
    """
    if da.ndim < 2:
        raise ValueError(f"Expected at least 2D DataArray, got {da.ndim}D")

    y_dim, x_dim = find_spatial_dims(da)
    time_dim = find_time_dim(da)
    other_dims = non_spatial_dims(da, y_dim, x_dim)
    # Prefer time as the outermost leading axis when present (CF T)
    if time_dim is not None and time_dim in other_dims:
        other_dims = [time_dim] + [d for d in other_dims if d != time_dim]
    # Spatial axes last for nd helpers: (..., y, x)
    ordered = other_dims + [y_dim, x_dim]
    transposed = da.transpose(*ordered)
    values = np.asarray(transposed.values)
    filled = nd_func(values, **kwargs)
    out = xr.DataArray(
        filled,
        dims=transposed.dims,
        coords={k: transposed.coords[k] for k in transposed.dims if k in transposed.coords},
        name=da.name,
        attrs=dict(da.attrs),
    )
    # Restore original dim order and non-dimensional coords
    out = out.transpose(*da.dims)
    for coord_name, coord in da.coords.items():
        if coord_name not in out.coords:
            out = out.assign_coords({coord_name: coord})
    return out


def _fill_dataarray(
    da: xr.DataArray,
    method: str,
    **kwargs,
) -> xr.DataArray:
    """Dispatch one DataArray to the selected fill methodology.

    Parameters
    ----------
    da : xarray.DataArray
        Field to fill.
    method : str
        Algorithm name (case-insensitive). Accepted aliases:

        * Gaussian: ``"gaussian"``, ``"gaussian_blur"``, ``"gs"``
        * Iterative: ``"iterative"``, ``"iterative_diffusion"``, ``"diffusion"``
    **kwargs
        Method-specific options. Unexpected keys raise ``TypeError``.

        Gaussian
            ``stddev``, ``max_passes``, ``parallel``, ``max_workers``,
            ``verbose``
        Iterative
            ``max_iter``, ``tol``, ``parallel``, ``max_workers``,
            ``verbose``

    Returns
    -------
    xarray.DataArray
        Filled DataArray.

    Raises
    ------
    TypeError
        If keyword arguments do not belong to the chosen method.
    ValueError
        If ``method`` is not recognized.
    """
    method = method.lower()
    if method in ("gaussian", "gaussian_blur", "gs"):
        stddev = kwargs.pop("stddev", 1.0)
        max_passes = kwargs.pop("max_passes", 64)
        parallel = kwargs.pop("parallel", True)
        max_workers = kwargs.pop("max_workers", None)
        verbose = kwargs.pop("verbose", False)
        if kwargs:
            raise TypeError(f"Unexpected kwargs for gaussian: {sorted(kwargs)}")
        return _apply_nd_to_dataarray(
            da,
            gaussian_fill_nd,
            stddev=stddev,
            max_passes=max_passes,
            parallel=parallel,
            max_workers=max_workers,
            verbose=verbose,
        )

    if method in ("iterative", "iterative_diffusion", "diffusion"):
        max_iter = kwargs.pop("max_iter", 500)
        tol = kwargs.pop("tol", 1e-5)
        parallel = kwargs.pop("parallel", True)
        max_workers = kwargs.pop("max_workers", None)
        verbose = kwargs.pop("verbose", False)
        if kwargs:
            raise TypeError(f"Unexpected kwargs for iterative: {sorted(kwargs)}")
        return _apply_nd_to_dataarray(
            da,
            inpaint_nans_nd,
            max_iter=max_iter,
            tol=tol,
            parallel=parallel,
            max_workers=max_workers,
            verbose=verbose,
        )

    raise ValueError(
        f"Unknown method {method!r}. Use 'gaussian' or 'iterative'."
    )


def fill_nans(
    obj: ArrayLike,
    method: str = "gaussian",
    vars: Optional[Iterable[str]] = None,
    **kwargs,
) -> ArrayLike:
    """Fill NaN values in an xarray DataArray or Dataset.

    This is the main high-level API. Spatial planes are filled with either
    Gaussian kernel interpolation or iterative mean diffusion. Non-spatial
    dimensions (``time``, ``depth``, …) are processed slice-by-slice.
    Coordinates, dimension order, variable names, and attributes are
    preserved; only data values change.

    Parameters
    ----------
    obj : xarray.DataArray or xarray.Dataset
        Input object containing NaNs to fill. Spatial (Y/X) and time (T)
        axes are detected from CF coordinate metadata (``standard_name``,
        ``axis``, ``units``), independent of dimension labels; common
        names such as ``lat``/``lon``/``time`` remain a fallback.
    method : {"gaussian", "iterative"}, default "gaussian"
        Fill algorithm. Aliases:

        * ``"gaussian"`` / ``"gaussian_blur"`` / ``"gs"``
        * ``"iterative"`` / ``"iterative_diffusion"`` / ``"diffusion"``
    vars : iterable of str or None, default None
        Dataset only: which ``data_vars`` to process. ``None`` selects all
        numeric data variables. Ignored (and forbidden) for DataArray input.
    **kwargs
        Forwarded to the chosen method.

        For ``method="gaussian"``
            * **stddev** (float, default 1.0) — initial Gaussian kernel
              standard deviation.
            * **max_passes** (int, default 64) — max interpolate passes;
              kernel grows when a pass stalls.
            * **parallel** (bool, default True) — thread over non-spatial
              slices.
            * **max_workers** (int or None) — thread pool size.
            * **verbose** (bool, default False) — print progress.

        For ``method="iterative"``
            * **max_iter** (int, default 500) — max diffusion iterations
              per slice.
            * **tol** (float, default 1e-5) — convergence tolerance.
            * **parallel**, **max_workers**, **verbose** — same meaning as
              above.

    Returns
    -------
    xarray.DataArray or xarray.Dataset
        Same type as ``obj``. For Datasets, only selected variables are
        replaced; others (including non-numeric flags) are unchanged.

    Raises
    ------
    TypeError
        If ``obj`` is not a DataArray/Dataset, if ``vars`` is passed with
        a DataArray, or if unexpected kwargs are supplied for the method.
    KeyError
        If a name in ``vars`` is missing from the Dataset.
    ValueError
        If ``method`` is unknown or spatial dimensions cannot be found.

    Notes
    -----
    * This function does **not** read or write NetCDF files. Use
      ``xr.open_dataset`` / ``ds.to_netcdf`` in the caller.
    * Land-mask cropping (BMKG / Natural Earth) is intentionally out of
      scope; apply masks before or after this call as needed.

    Examples
    --------
    Fill a single DataArray with Gaussian smoothing::

        from inpaint import fill_nans
        da_out = fill_nans(ds["hs"], method="gaussian", stddev=1.0)

    Fill selected variables on a Dataset with iterative diffusion::

        ds_out = fill_nans(
            ds, method="iterative", vars=["hs", "t01"], max_iter=300
        )

    See Also
    --------
    gaussian_blur : Shortcut for ``method="gaussian"``.
    iterative_diffusion : Shortcut for ``method="iterative"``.
    DataArray.inpaint.fill : Accessor form for DataArrays.
    Dataset.inpaint.fill : Accessor form for Datasets.
    """
    if isinstance(obj, xr.DataArray):
        if vars is not None:
            raise TypeError("'vars' is only valid for Dataset input")
        return _fill_dataarray(obj, method=method, **kwargs)

    if isinstance(obj, xr.Dataset):
        target_vars = list(vars) if vars is not None else _numeric_data_vars(obj)
        missing = [v for v in target_vars if v not in obj.data_vars]
        if missing:
            raise KeyError(f"Variables not in Dataset: {missing}")

        updates = {
            name: _fill_dataarray(obj[name], method=method, **kwargs)
            for name in target_vars
        }
        return obj.assign(updates)

    raise TypeError(
        f"Expected xr.DataArray or xr.Dataset, got {type(obj).__name__}"
    )


def iterative_diffusion(
    obj: ArrayLike,
    vars: Optional[Iterable[str]] = None,
    max_iter: int = 500,
    tol: float = 1e-5,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    verbose: bool = False,
) -> ArrayLike:
    """Fill NaNs with iterative mean diffusion (Laplace-style inpainting).

    Shortcut for :func:`fill_nans` with ``method="iterative"``. Missing
    cells are seeded with the field mean and repeatedly replaced by their
    3×3 neighborhood average until convergence.

    Parameters
    ----------
    obj : xarray.DataArray or xarray.Dataset
        Input object to fill.
    vars : iterable of str or None, default None
        Dataset only: variables to process. ``None`` → all numeric
        ``data_vars``. Must be omitted for DataArray input.
    max_iter : int, default 500
        Maximum diffusion iterations per spatial slice.
    tol : float, default 1e-5
        Stop when the max absolute update on NaN cells is below this value.
    parallel : bool, default True
        Parallelize over non-spatial slices via a thread pool.
    max_workers : int or None, default None
        Thread pool size (``None`` = executor default).
    verbose : bool, default False
        Print per-call progress from the numpy backend.

    Returns
    -------
    xarray.DataArray or xarray.Dataset
        Same type as ``obj``, with NaNs filled on the selected variables.

    Raises
    ------
    TypeError, KeyError, ValueError
        Same conditions as :func:`fill_nans`.

    Examples
    --------
    >>> from inpaint import iterative_diffusion  # doctest: +SKIP
    >>> da_out = iterative_diffusion(da, max_iter=200, parallel=False)  # doctest: +SKIP
    >>> ds_out = iterative_diffusion(ds, vars=["hs"])  # doctest: +SKIP

    See Also
    --------
    fill_nans : Generic dispatcher for both methodologies.
    gaussian_blur : Gaussian kernel alternative.
    inpaint_nans_2d : Low-level numpy 2-D solver.
    """
    return fill_nans(
        obj,
        method="iterative",
        vars=vars,
        max_iter=max_iter,
        tol=tol,
        parallel=parallel,
        max_workers=max_workers,
        verbose=verbose,
    )


def gaussian_blur(
    obj: ArrayLike,
    vars: Optional[Iterable[str]] = None,
    stddev: float = 1.0,
    max_passes: int = 64,
    parallel: bool = True,
    max_workers: Optional[int] = None,
    verbose: bool = False,
) -> ArrayLike:
    """Fill NaNs with multi-pass Gaussian kernel interpolation.

    Shortcut for :func:`fill_nans` with ``method="gaussian"``. Uses Astropy
    ``interpolate_replace_nans``; large holes are closed by repeating passes
    and growing the kernel when progress stalls.

    Parameters
    ----------
    obj : xarray.DataArray or xarray.Dataset
        Input object to fill.
    vars : iterable of str or None, default None
        Dataset only: variables to process. ``None`` → all numeric
        ``data_vars``. Must be omitted for DataArray input.
    stddev : float, default 1.0
        Initial Gaussian kernel standard deviation (``x_stddev``).
    max_passes : int, default 64
        Maximum interpolate passes per spatial slice.
    parallel : bool, default True
        Parallelize over non-spatial slices via a thread pool.
    max_workers : int or None, default None
        Thread pool size (``None`` = executor default).
    verbose : bool, default False
        Print per-call progress from the numpy backend.

    Returns
    -------
    xarray.DataArray or xarray.Dataset
        Same type as ``obj``, with NaNs filled on the selected variables.

    Raises
    ------
    TypeError, KeyError, ValueError
        Same conditions as :func:`fill_nans`.

    Examples
    --------
    >>> from inpaint import gaussian_blur  # doctest: +SKIP
    >>> da_out = gaussian_blur(da, stddev=1.5, parallel=False)  # doctest: +SKIP
    >>> ds_out = gaussian_blur(ds, vars=["hs", "t01"])  # doctest: +SKIP

    See Also
    --------
    fill_nans : Generic dispatcher for both methodologies.
    iterative_diffusion : Iterative diffusion alternative.
    gaussian_fill_2d : Low-level numpy 2-D solver.
    """
    return fill_nans(
        obj,
        method="gaussian",
        vars=vars,
        stddev=stddev,
        max_passes=max_passes,
        parallel=parallel,
        max_workers=max_workers,
        verbose=verbose,
    )
