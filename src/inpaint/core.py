"""
xarray-facing API: accept Dataset/DataArray, return the same type.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import xarray as xr

from .gaussian_blur import gaussian_fill_nd
from .iterative_diffusion import inpaint_nans_nd

ArrayLike = Union[xr.DataArray, xr.Dataset]

_SPATIAL_CANDIDATES: Tuple[Tuple[str, str], ...] = (
    ("lat", "lon"),
    ("latitude", "longitude"),
    ("y", "x"),
)


def _find_spatial_dims(dims: Sequence[str]) -> Tuple[str, str]:
    dim_set = set(dims)
    for y_name, x_name in _SPATIAL_CANDIDATES:
        if y_name in dim_set and x_name in dim_set:
            return y_name, x_name
    raise ValueError(
        "Could not find spatial dimensions. Expected one of "
        f"{list(_SPATIAL_CANDIDATES)}; got {list(dims)}"
    )


def _numeric_data_vars(ds: xr.Dataset) -> List[str]:
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
    if da.ndim < 2:
        raise ValueError(f"Expected at least 2D DataArray, got {da.ndim}D")

    y_dim, x_dim = _find_spatial_dims(da.dims)
    other_dims = [d for d in da.dims if d not in (y_dim, x_dim)]
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
    """
    Fill NaN values in an xarray object.

    Args:
        obj: ``xr.DataArray`` or ``xr.Dataset``
        method: ``"gaussian"`` or ``"iterative"``
        vars: For Dataset only — variable names to process.
            ``None`` means all numeric data variables.
        **kwargs: Method-specific options
            - gaussian: ``stddev``, ``max_passes``, ``parallel``, ``max_workers``, ``verbose``
            - iterative: ``max_iter``, ``tol``, ``parallel``, ``max_workers``, ``verbose``

    Returns:
        Same type as ``obj``, with NaNs filled on selected variables.
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
    """Shortcut for ``fill_nans(..., method='iterative')``."""
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
    """Shortcut for ``fill_nans(..., method='gaussian')``."""
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
