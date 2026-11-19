"""xarray accessors: ``da.inpaint.fill(...)`` / ``ds.inpaint.fill(...)``.

Importing :mod:`inpaint` registers these accessors automatically via
:func:`xarray.register_dataarray_accessor` and
:func:`xarray.register_dataset_accessor`. Usage mirrors high-level helpers
in :mod:`inpaint.core` while keeping a fluent, xarray-native style.
"""

from __future__ import annotations

from typing import Iterable, Optional

import xarray as xr

from .core import fill_nans


@xr.register_dataarray_accessor("inpaint")
class DataArrayInpaintAccessor:
    """``.inpaint`` accessor attached to every :class:`xarray.DataArray`.

    Provides coastal / gap NaN filling without leaving the xarray namespace.

    Examples
    --------
    >>> da_filled = da.inpaint.fill(method="gaussian", stddev=1.0)  # doctest: +SKIP
    >>> da_filled = da.inpaint.fill(method="iterative", max_iter=300)  # doctest: +SKIP
    """

    def __init__(self, obj: xr.DataArray):
        """Bind the accessor to a DataArray instance.

        Parameters
        ----------
        obj : xarray.DataArray
            The DataArray on which ``.inpaint`` was accessed. Stored as
            ``self._obj`` and never modified in place.
        """
        self._obj = obj

    def fill(self, method: str = "gaussian", **kwargs) -> xr.DataArray:
        """Fill NaN values on this DataArray.

        Parameters
        ----------
        method : {"gaussian", "iterative"}, default "gaussian"
            Fill algorithm. See :func:`inpaint.core.fill_nans` for aliases
            and full parameter documentation.
        **kwargs
            Method-specific options, for example:

            * Gaussian: ``stddev``, ``max_passes``, ``parallel``,
              ``max_workers``, ``verbose``
            * Iterative: ``max_iter``, ``tol``, ``parallel``,
              ``max_workers``, ``verbose``

        Returns
        -------
        xarray.DataArray
            New DataArray with NaNs filled. Dims, coords, name, and attrs
            match the original; the input is not mutated.

        Raises
        ------
        TypeError, ValueError
            Propagated from :func:`inpaint.core.fill_nans` (unknown method,
            unexpected kwargs, missing spatial dims, etc.).

        Examples
        --------
        >>> out = ds["hs"].inpaint.fill(method="gaussian", stddev=1.0)  # doctest: +SKIP

        See Also
        --------
        inpaint.core.fill_nans
        inpaint.core.gaussian_blur
        inpaint.core.iterative_diffusion
        DatasetInpaintAccessor.fill
        """
        return fill_nans(self._obj, method=method, **kwargs)


@xr.register_dataset_accessor("inpaint")
class DatasetInpaintAccessor:
    """``.inpaint`` accessor attached to every :class:`xarray.Dataset`.

    Applies NaN filling to one or more data variables and returns an
    updated Dataset via ``assign`` (original object is not mutated).

    Examples
    --------
    >>> ds2 = ds.inpaint.fill(method="iterative", vars=["hs"])  # doctest: +SKIP
    >>> ds2 = ds.inpaint.fill(method="gaussian")  # all numeric vars  # doctest: +SKIP
    """

    def __init__(self, obj: xr.Dataset):
        """Bind the accessor to a Dataset instance.

        Parameters
        ----------
        obj : xarray.Dataset
            The Dataset on which ``.inpaint`` was accessed. Stored as
            ``self._obj`` and never modified in place.
        """
        self._obj = obj

    def fill(
        self,
        method: str = "gaussian",
        vars: Optional[Iterable[str]] = None,
        **kwargs,
    ) -> xr.Dataset:
        """Fill NaN values on selected Dataset variables.

        Parameters
        ----------
        method : {"gaussian", "iterative"}, default "gaussian"
            Fill algorithm. See :func:`inpaint.core.fill_nans` for aliases
            and full parameter documentation.
        vars : iterable of str or None, default None
            Variable names to process. ``None`` selects all numeric
            ``data_vars``. Non-selected variables are copied through
            unchanged.
        **kwargs
            Method-specific options (``stddev``, ``max_iter``, ``tol``,
            ``parallel``, …) forwarded to :func:`inpaint.core.fill_nans`.

        Returns
        -------
        xarray.Dataset
            New Dataset with filled variables assigned. The input Dataset
            is not mutated.

        Raises
        ------
        KeyError
            If a name in ``vars`` is not present in the Dataset.
        TypeError, ValueError
            Propagated from :func:`inpaint.core.fill_nans`.

        Examples
        --------
        >>> out = ds.inpaint.fill(method="gaussian", vars=["hs", "t01"])  # doctest: +SKIP

        See Also
        --------
        inpaint.core.fill_nans
        DataArrayInpaintAccessor.fill
        """
        return fill_nans(self._obj, method=method, vars=vars, **kwargs)
