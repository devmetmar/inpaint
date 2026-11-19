"""Tests for Gaussian blur methodology."""

import numpy as np
import pytest

from inpaint.gaussian_blur import gaussian_fill_2d, gaussian_fill_nd
from inpaint.gaussian_blur import test_gaussian_blur as run_gaussian_selfcheck


def test_gaussian_fill_2d_fills_hole(synthetic_2d):
    raw, truth, hole = synthetic_2d
    filled = gaussian_fill_2d(raw, stddev=1.0)

    assert filled.shape == raw.shape
    assert filled.dtype == np.float32
    assert not np.isnan(filled).any()
    assert np.isnan(raw[hole]).all()

    rmse = float(np.sqrt(np.mean((filled[hole] - truth[hole]) ** 2)))
    assert rmse < 0.5


def test_gaussian_fill_2d_no_nan_passthrough():
    data = np.ones((10, 12), dtype=np.float64)
    out = gaussian_fill_2d(data)
    np.testing.assert_allclose(out, data.astype(np.float32))


def test_gaussian_fill_2d_rejects_non_2d():
    with pytest.raises(ValueError, match="Expected 2D"):
        gaussian_fill_2d(np.zeros((2, 3, 4)))


def test_gaussian_fill_nd(synthetic_2d):
    raw, _, _ = synthetic_2d
    stack = np.stack([raw, raw], axis=0)
    filled = gaussian_fill_nd(stack, stddev=1.0, parallel=False, verbose=False)

    assert filled.shape == stack.shape
    assert not np.isnan(filled).any()


def test_gaussian_blur_selfcheck_runs():
    """Module-level demo/self-check should complete without error."""
    run_gaussian_selfcheck()
