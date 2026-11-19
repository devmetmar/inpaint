"""Shared fixtures for inpaint tests."""

import numpy as np
import pytest
import xarray as xr


@pytest.fixture
def synthetic_2d():
    """2D field with a circular NaN hole; returns (raw_with_nan, truth, hole_mask)."""
    ny, nx = 40, 50
    y, x = np.mgrid[0:ny, 0:nx]
    truth = (np.sin(x / 8.0) * np.cos(y / 8.0) + x / 40.0).astype(np.float64)
    hole = ((x - nx // 2) ** 2 + (y - ny // 2) ** 2) < 64
    raw = truth.copy()
    raw[hole] = np.nan
    return raw, truth, hole


@pytest.fixture
def synthetic_dataarray(synthetic_2d):
    """xr.DataArray (time, lat, lon) with NaN hole on each timestep."""
    raw, truth, hole = synthetic_2d
    ny, nx = raw.shape
    da = xr.DataArray(
        np.stack([raw, raw], axis=0).astype(np.float32),
        dims=("time", "lat", "lon"),
        coords={
            "time": [0, 1],
            "lat": np.arange(ny),
            "lon": np.arange(nx),
        },
        name="hs",
        attrs={"units": "m"},
    )
    return da, truth.astype(np.float32), hole


@pytest.fixture
def synthetic_dataset(synthetic_dataarray):
    da, truth, hole = synthetic_dataarray
    ds = xr.Dataset(
        {
            "hs": da,
            "t01": da.copy(deep=True),
            "flag": (("lat", "lon"), np.zeros(da.shape[1:], dtype=np.int8)),
        }
    )
    return ds, truth, hole
