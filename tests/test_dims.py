"""Tests for CF / NetCDF Conventions dimension detection."""

import numpy as np
import pytest
import xarray as xr

from inpaint import describe_axes, fill_nans, find_spatial_dims, find_time_dim
from inpaint.dims import classify_dim


def _cf_dataarray_odd_names():
    """Dims named TSTEP/ROW/COL but CF standard_name on coordinates."""
    nt, ny, nx = 2, 12, 15
    raw = np.ones((nt, ny, nx), dtype=np.float32)
    raw[:, 4:8, 5:10] = np.nan
    da = xr.DataArray(
        raw,
        dims=("TSTEP", "ROW", "COL"),
        coords={
            "TSTEP": ("TSTEP", np.arange(nt)),
            "ROW": ("ROW", np.linspace(-10, 0, ny)),
            "COL": ("COL", np.linspace(100, 110, nx)),
        },
        name="hs",
    )
    da["TSTEP"].attrs["standard_name"] = "time"
    da["TSTEP"].attrs["units"] = "hours since 2024-01-01 00:00:00"
    da["ROW"].attrs["standard_name"] = "latitude"
    da["ROW"].attrs["units"] = "degrees_north"
    da["COL"].attrs["standard_name"] = "longitude"
    da["COL"].attrs["units"] = "degrees_east"
    return da


def test_classify_from_standard_name():
    da = _cf_dataarray_odd_names()
    assert classify_dim(da, "ROW") == "Y"
    assert classify_dim(da, "COL") == "X"
    assert classify_dim(da, "TSTEP") == "T"


def test_find_spatial_and_time_from_cf():
    da = _cf_dataarray_odd_names()
    assert find_spatial_dims(da) == ("ROW", "COL")
    assert find_time_dim(da) == "TSTEP"
    info = describe_axes(da)
    assert info["y"] == "ROW"
    assert info["x"] == "COL"
    assert info["time"] == "TSTEP"


def test_axis_attribute_detection():
    da = xr.DataArray(
        np.ones((3, 4, 5)),
        dims=("a", "b", "c"),
        coords={
            "a": ("a", np.arange(3)),
            "b": ("b", np.arange(4)),
            "c": ("c", np.arange(5)),
        },
    )
    da["a"].attrs["axis"] = "T"
    da["b"].attrs["axis"] = "Y"
    da["c"].attrs["axis"] = "X"
    assert find_spatial_dims(da) == ("b", "c")
    assert find_time_dim(da) == "a"


def test_units_based_detection():
    da = xr.DataArray(
        np.ones((2, 3, 4)),
        dims=("t0", "j", "i"),
        coords={
            "t0": ("t0", np.arange(2)),
            "j": ("j", np.linspace(-5, 5, 3)),
            "i": ("i", np.linspace(10, 20, 4)),
        },
    )
    da["t0"].attrs["units"] = "days since 2000-01-01"
    da["j"].attrs["units"] = "degrees_north"
    da["i"].attrs["units"] = "degrees_east"
    assert find_spatial_dims(da) == ("j", "i")
    assert find_time_dim(da) == "t0"


def test_name_fallback_still_works():
    da = xr.DataArray(
        np.ones((2, 5, 6)),
        dims=("time", "lat", "lon"),
        coords={
            "time": np.arange(2),
            "lat": np.arange(5),
            "lon": np.arange(6),
        },
    )
    assert find_spatial_dims(da) == ("lat", "lon")
    assert find_time_dim(da) == "time"


def test_fill_nans_with_cf_odd_dim_names():
    da = _cf_dataarray_odd_names()
    out = fill_nans(da, method="iterative", max_iter=100, parallel=False)
    assert out.dims == da.dims
    assert not np.isnan(out.values).any()


def test_missing_cf_and_names_raises():
    da = xr.DataArray(np.ones((2, 3, 4)), dims=("a", "b", "c"))
    with pytest.raises(ValueError, match="Could not find spatial dimensions"):
        find_spatial_dims(da)
