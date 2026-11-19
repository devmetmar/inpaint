"""Tests for iterative diffusion methodology."""

import numpy as np
import pytest

from inpaint.iterative_diffusion import (
    inpaint_nans_2d,
    inpaint_nans_3d,
    inpaint_nans_nd,
)
from inpaint.iterative_diffusion import (
    test_iterative_diffusion as run_iterative_selfcheck,
)


def test_inpaint_nans_2d_fills_hole(synthetic_2d):
    raw, truth, hole = synthetic_2d
    filled = inpaint_nans_2d(raw, max_iter=300, tol=1e-5)

    assert filled.shape == raw.shape
    assert filled.dtype == np.float32
    assert not np.isnan(filled).any()
    assert np.isnan(raw[hole]).all()

    rmse = float(np.sqrt(np.mean((filled[hole] - truth[hole]) ** 2)))
    assert rmse < 0.2


def test_inpaint_nans_2d_no_nan_passthrough():
    data = np.ones((10, 12), dtype=np.float64)
    out = inpaint_nans_2d(data)
    np.testing.assert_allclose(out, data.astype(np.float32))


def test_inpaint_nans_2d_rejects_non_2d():
    with pytest.raises(ValueError, match="Expected 2D"):
        inpaint_nans_2d(np.zeros((2, 3, 4)))


def test_inpaint_nans_3d_and_nd(synthetic_2d):
    raw, _, hole = synthetic_2d
    stack = np.stack([raw, raw, raw], axis=0)

    filled_3d = inpaint_nans_3d(stack, max_iter=200, parallel=False, verbose=False)
    filled_nd = inpaint_nans_nd(stack, max_iter=200, parallel=False, verbose=False)

    assert filled_3d.shape == stack.shape
    assert filled_nd.shape == stack.shape
    assert not np.isnan(filled_3d).any()
    assert not np.isnan(filled_nd).any()
    np.testing.assert_allclose(filled_3d, filled_nd, rtol=1e-5)


def test_iterative_diffusion_selfcheck_runs():
    """Module-level demo/self-check should complete without error."""
    run_iterative_selfcheck()
