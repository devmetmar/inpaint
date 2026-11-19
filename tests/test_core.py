"""Tests for xarray-facing API covering both methodologies."""

import numpy as np
import pytest
import xarray as xr

from inpaint import fill_nans, gaussian_blur, iterative_diffusion


@pytest.mark.parametrize("method", ["iterative", "gaussian"])
def test_fill_nans_dataarray_both_methods(synthetic_dataarray, method):
    da, _, _ = synthetic_dataarray
    kwargs = (
        {"max_iter": 200, "parallel": False}
        if method == "iterative"
        else {"stddev": 1.0, "parallel": False}
    )
    out = fill_nans(da, method=method, **kwargs)

    assert isinstance(out, xr.DataArray)
    assert out.dims == da.dims
    assert out.name == da.name
    assert out.attrs.get("units") == "m"
    assert not np.isnan(out.values).any()


@pytest.mark.parametrize("method", ["iterative", "gaussian"])
def test_fill_nans_dataset_selective_vars(synthetic_dataset, method):
    ds, _, _ = synthetic_dataset
    kwargs = (
        {"max_iter": 200, "parallel": False}
        if method == "iterative"
        else {"stddev": 1.0, "parallel": False}
    )
    out = fill_nans(ds, method=method, vars=["hs"], **kwargs)

    assert isinstance(out, xr.Dataset)
    assert not np.isnan(out["hs"].values).any()
    assert int(np.isnan(out["t01"].values).sum()) == int(np.isnan(ds["t01"].values).sum())
    np.testing.assert_array_equal(out["flag"].values, ds["flag"].values)


def test_shortcuts_and_accessors(synthetic_dataarray, synthetic_dataset):
    da, _, _ = synthetic_dataarray
    ds, _, _ = synthetic_dataset

    out_i = iterative_diffusion(da, max_iter=150, parallel=False)
    out_g = gaussian_blur(ds, vars=["t01"], stddev=1.0, parallel=False)

    assert isinstance(out_i, xr.DataArray)
    assert isinstance(out_g, xr.Dataset)
    assert not np.isnan(out_i.values).any()
    assert not np.isnan(out_g["t01"].values).any()

    assert not np.isnan(da.inpaint.fill(method="gaussian", parallel=False).values).any()
    assert not np.isnan(
        ds.inpaint.fill(method="iterative", vars=["hs"], parallel=False)["hs"].values
    ).any()


def test_unknown_method_raises(synthetic_dataarray):
    da, _, _ = synthetic_dataarray
    with pytest.raises(ValueError, match="Unknown method"):
        fill_nans(da, method="magic")
