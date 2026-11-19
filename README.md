# inpaint

Coastal NaN fill / extrapolation for **xarray** (`DataArray` / `Dataset`).

Algorithms only — no NetCDF I/O. Open and save files yourself with xarray.

## Install

```bash
pip install -e /path/to/pkgs/inpaint
```

## Usage

```python
import xarray as xr
from inpaint import fill_nans, iterative_diffusion, gaussian_blur

ds = xr.open_dataset("wave.nc")

# DataArray
da = fill_nans(ds["hs"], method="gaussian", stddev=1.0)
da = fill_nans(ds["hs"], method="iterative", max_iter=500, tol=1e-5)

# Dataset (vars=None → all numeric data_vars)
ds_out = fill_nans(ds, method="gaussian", vars=["hs", "t01"])

# Shortcuts
da2 = iterative_diffusion(ds["hs"])
ds2 = gaussian_blur(ds, vars=["hs"], stddev=1.0)

# xarray accessor
da3 = ds["hs"].inpaint.fill(method="gaussian", stddev=1.0)
ds3 = ds.inpaint.fill(method="iterative", vars=["hs"])
```

## Methods

| Method | Key params | Backend |
|--------|------------|---------|
| `gaussian` | `stddev`, `max_passes` | Astropy `interpolate_replace_nans` (multi-pass) |
| `iterative` | `max_iter`, `tol`, `parallel` | SciPy mean diffusion |

Spatial (Y/X) and time (T) dims are detected from **CF/NetCDF Conventions** on coordinates — `standard_name`, `axis`, then `units` — so labels like `ROW`/`COL`/`TSTEP` work if metadata is present. Common names (`lat`/`lon`/`time`) are a fallback. Other dims are processed slice-by-slice.

```python
from inpaint import describe_axes
describe_axes(ds["hs"])  # {'dims': {...}, 'y': ..., 'x': ..., 'time': ...}
```

## Tests

```bash
pip install -e ".[test]"
pytest
```

Self-checks (no pytest required):

```python
from inpaint import test_iterative_diffusion, test_gaussian_blur

test_iterative_diffusion()
test_gaussian_blur()
```
