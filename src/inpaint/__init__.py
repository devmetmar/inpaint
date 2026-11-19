"""Coastal NaN fill / extrapolation for xarray."""

from .core import fill_nans, gaussian_blur, iterative_diffusion
from .gaussian_blur import gaussian_fill_2d, gaussian_fill_nd
from .iterative_diffusion import inpaint_nans_2d, inpaint_nans_3d, inpaint_nans_nd

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
    "__version__",
]
