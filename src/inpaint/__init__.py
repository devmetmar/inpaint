"""Coastal NaN fill / extrapolation for xarray.

This package provides algorithms to fill missing (``NaN``) values in gridded
oceanographic or atmospheric fields — typically coastal / land-adjacent gaps —
and returns the same ``xarray`` type that was passed in.

**Algorithms**

* **Gaussian blur** (`gaussian_blur`, ``method="gaussian"``): Astropy
  ``interpolate_replace_nans`` with a 2-D Gaussian kernel. Good for smooth
  coastal extrapolation; uses multi-pass filling for large holes.
* **Iterative diffusion** (`iterative_diffusion`, ``method="iterative"``):
  repeated 3×3 mean filtering on NaN cells until convergence (Laplace-like
  inpainting, similar to MATLAB ``inpaint_nans`` method 4).

**Typical usage**

>>> import xarray as xr
>>> from inpaint import fill_nans
>>> ds = xr.open_dataset("wave.nc")  # doctest: +SKIP
>>> ds_filled = fill_nans(ds, method="gaussian", vars=["hs"])  # doctest: +SKIP
>>> da_filled = ds["hs"].inpaint.fill(method="iterative")  # doctest: +SKIP

I/O (``open_dataset`` / ``to_netcdf``) stays with the caller; this package
only transforms arrays in memory.
"""

from .core import fill_nans, gaussian_blur, iterative_diffusion
from .dims import classify_dim, describe_axes, find_spatial_dims, find_time_dim
from .gaussian_blur import gaussian_fill_2d, gaussian_fill_nd, test_gaussian_blur
from .iterative_diffusion import (
    inpaint_nans_2d,
    inpaint_nans_3d,
    inpaint_nans_nd,
    test_inpaint,
    test_iterative_diffusion,
)

# Register .inpaint accessors on import
from . import accessors as _accessors  # noqa: F401

__version__ = "0.1.0"

__all__ = [
    "fill_nans",
    "gaussian_blur",
    "iterative_diffusion",
    "gaussian_fill_2d",
    "gaussian_fill_nd",
    "inpaint_nans_2d",
    "inpaint_nans_3d",
    "inpaint_nans_nd",
    "classify_dim",
    "describe_axes",
    "find_spatial_dims",
    "find_time_dim",
    "test_gaussian_blur",
    "test_iterative_diffusion",
    "test_inpaint",
    "__version__",
]
