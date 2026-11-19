"""xarray accessors: ``da.inpaint.fill(...)`` / ``ds.inpaint.fill(...)``."""

from __future__ import annotations

from typing import Iterable, Optional

import xarray as xr

from .core import fill_nans


@xr.register_dataarray_accessor("inpaint")
class DataArrayInpaintAccessor:
    def __init__(self, obj: xr.DataArray):
        self._obj = obj

    def fill(self, method: str = "gaussian", **kwargs) -> xr.DataArray:
        """Fill NaNs; see :func:`inpaint.core.fill_nans`."""
        return fill_nans(self._obj, method=method, **kwargs)


@xr.register_dataset_accessor("inpaint")
class DatasetInpaintAccessor:
    def __init__(self, obj: xr.Dataset):
        self._obj = obj

    def fill(
        self,
        method: str = "gaussian",
        vars: Optional[Iterable[str]] = None,
        **kwargs,
    ) -> xr.Dataset:
        """Fill NaNs; see :func:`inpaint.core.fill_nans`."""
        return fill_nans(self._obj, method=method, vars=vars, **kwargs)
