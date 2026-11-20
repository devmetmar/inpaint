"""L1 extras: scipy-weighted gaussian preserves valid pixels; parallel OK."""

from __future__ import annotations

import numpy as np
import pytest

from inpaint.gaussian_blur import gaussian_fill_2d, gaussian_fill_nd
from inpaint import fill_nans
import xarray as xr


def test_valid_pixels_bit_identical():
    rng = np.random.default_rng(0)
    data = rng.normal(size=(40, 50))
    hole = np.zeros_like(data, dtype=bool)
    hole[15:20, 20:28] = True
    raw = data.copy()
    raw[hole] = np.nan
    out = gaussian_fill_2d(raw, stddev=1.0, max_passes=8)
    valid = ~hole
    np.testing.assert_array_equal(out[valid], data[valid].astype(np.float32))
    assert not np.isnan(out[hole]).any()


def test_parallel_matches_serial_on_holes():
    rng = np.random.default_rng(1)
    base = rng.normal(size=(30, 30))
    hole = np.zeros_like(base, dtype=bool)
    hole[10:14, 10:14] = True
    raw = base.copy()
    raw[hole] = np.nan
    stack = np.stack([raw, raw, raw], axis=0)
    a = gaussian_fill_nd(stack, stddev=1.0, max_passes=8, parallel=False)
    b = gaussian_fill_nd(stack, stddev=1.0, max_passes=8, parallel=True, max_workers=2)
    # valid exact; holes close
    valid = np.broadcast_to(~hole, stack.shape)
    np.testing.assert_array_equal(a[valid], b[valid])
    np.testing.assert_allclose(a[~valid], b[~valid], rtol=1e-5, atol=1e-5)


def test_fill_nans_forwards_max_passes():
    da = xr.DataArray(
        [[1.0, np.nan], [1.0, 1.0]],
        dims=("lat", "lon"),
        coords={"lat": [0.0, 1.0], "lon": [0.0, 1.0]},
    )
    out = fill_nans(da, method="gaussian", stddev=1.0, max_passes=4, parallel=False)
    assert not np.isnan(out.values).any()
