"""CF / NetCDF Conventions dimension detection for xarray objects.

Spatial (Y/X) and time (T) dimensions are identified from coordinate
metadata first, then fall back to common dimension *names* only if
attributes are missing. Dimension labels such as ``ROW`` / ``COL`` /
``TSTEP`` are therefore fine as long as the coordinates carry CF
``standard_name``, ``axis``, or conventional ``units``.

References
----------
* CF Conventions — `standard_name`, `axis`, and coordinate `units`
* https://cfconventions.org/
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import xarray as xr

# Name-based fallbacks (used only when CF attrs are absent)
_SPATIAL_NAME_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("lat", "lon"),
    ("latitude", "longitude"),
    ("y", "x"),
    ("Y", "X"),
    ("nlat", "nlon"),
    ("ny", "nx"),
    ("j", "i"),
    ("row", "col"),
    ("ROW", "COL"),
)

_TIME_NAMES = frozenset(
    {
        "time",
        "Time",
        "TIME",
        "t",
        "T",
        "tstep",
        "TSTEP",
        "ocean_time",
        "xtime",
    }
)

_LAT_STANDARD_NAMES = frozenset(
    {
        "latitude",
        "grid_latitude",
        "projection_y_coordinate",
    }
)
_LON_STANDARD_NAMES = frozenset(
    {
        "longitude",
        "grid_longitude",
        "projection_x_coordinate",
    }
)
_TIME_STANDARD_NAMES = frozenset(
    {
        "time",
        "forecast_reference_time",
    }
)

_LAT_UNITS_TOKENS = (
    "degrees_north",
    "degree_north",
    "degree_n",
    "degrees_n",
    "degreen",
    "degreesn",
)
_LON_UNITS_TOKENS = (
    "degrees_east",
    "degree_east",
    "degree_e",
    "degrees_e",
    "degreee",
    "degreese",
)


def _norm_units(units: object) -> str:
    if units is None:
        return ""
    text = str(units).strip().lower().replace(" ", "")
    return text


def _coords_for_dim(obj: xr.DataArray, dim: str) -> List[xr.DataArray]:
    """Return 1-D coordinates that describe ``dim`` (dim-coord + auxiliaries)."""
    found: List[xr.DataArray] = []
    seen = set()
    if dim in obj.coords:
        c = obj.coords[dim]
        found.append(c)
        seen.add(id(c))
    for name, c in obj.coords.items():
        if id(c) in seen:
            continue
        if c.ndim == 1 and c.dims == (dim,):
            found.append(c)
            seen.add(id(c))
    return found


def _classify_from_attrs(attrs: dict) -> Optional[str]:
    """Classify a coordinate as ``'Y'``, ``'X'``, ``'T'``, ``'Z'``, or ``None``.

    Priority: ``standard_name`` → ``axis`` → ``units``.
    """
    standard = str(attrs.get("standard_name", "") or "").strip().lower()
    if standard in _LAT_STANDARD_NAMES:
        return "Y"
    if standard in _LON_STANDARD_NAMES:
        return "X"
    if standard in _TIME_STANDARD_NAMES:
        return "T"
    if standard in {"height", "altitude", "depth", "air_pressure"}:
        return "Z"

    axis = str(attrs.get("axis", "") or "").strip().upper()
    if axis in {"Y", "X", "T", "Z"}:
        return axis

    units = _norm_units(attrs.get("units"))
    if units:
        if any(tok in units for tok in _LAT_UNITS_TOKENS) or units in {
            "degrees_north",
            "degree_north",
        }:
            return "Y"
        if any(tok in units for tok in _LON_UNITS_TOKENS) or units in {
            "degrees_east",
            "degree_east",
        }:
            return "X"
        # CF time units: "<time-unit> since <reference>"
        if "since" in units:
            return "T"

    return None


def classify_dim(obj: xr.DataArray, dim: str) -> Optional[str]:
    """Classify one dimension of a DataArray using CF metadata, then names.

    Parameters
    ----------
    obj : xarray.DataArray
        Array whose coordinates are inspected.
    dim : str
        Dimension name to classify.

    Returns
    -------
    {'Y', 'X', 'T', 'Z'} or None
        CF-style axis role, or ``None`` if unknown.
    """
    for coord in _coords_for_dim(obj, dim):
        role = _classify_from_attrs(dict(coord.attrs))
        if role is not None:
            return role

    # Name-based fallback (dimension label only)
    if dim in _TIME_NAMES:
        return "T"
    low = dim.lower()
    if low in {"lat", "latitude", "y", "nlat", "ny", "j", "row"}:
        return "Y"
    if low in {"lon", "longitude", "long", "x", "nlon", "nx", "i", "col"}:
        return "X"
    if low in {"depth", "lev", "level", "z", "height", "alt", "lay"}:
        return "Z"
    return None


def _roles_for_dims(obj: xr.DataArray) -> dict:
    return {dim: classify_dim(obj, dim) for dim in obj.dims}


def find_spatial_dims(obj: xr.DataArray) -> Tuple[str, str]:
    """Find ``(y_dim, x_dim)`` using CF attributes, then name pairs.

    Parameters
    ----------
    obj : xarray.DataArray
        Input field.

    Returns
    -------
    y_dim, x_dim : tuple of str
        Dimension names for the vertical/horizontal spatial axes on the
        model grid (latitude / projection_y and longitude / projection_x).

    Raises
    ------
    ValueError
        If a unique Y/X pair cannot be resolved.
    """
    roles = _roles_for_dims(obj)
    y_dims = [d for d, r in roles.items() if r == "Y"]
    x_dims = [d for d, r in roles.items() if r == "X"]

    if len(y_dims) == 1 and len(x_dims) == 1:
        return y_dims[0], x_dims[0]

    # Name-pair fallback (both members must be present)
    dim_set = set(obj.dims)
    for y_name, x_name in _SPATIAL_NAME_PAIRS:
        if y_name in dim_set and x_name in dim_set:
            return y_name, x_name

    raise ValueError(
        "Could not find spatial dimensions from CF metadata or names. "
        "Set coordinate standard_name/axis/units "
        f"(got roles={roles!r}, dims={list(obj.dims)!r})."
    )


def find_time_dim(obj: xr.DataArray) -> Optional[str]:
    """Find the time dimension using CF attributes, then common names.

    Parameters
    ----------
    obj : xarray.DataArray
        Input field.

    Returns
    -------
    str or None
        Time dimension name, or ``None`` if no time axis is present.
    """
    roles = _roles_for_dims(obj)
    t_dims = [d for d, r in roles.items() if r == "T"]
    if len(t_dims) == 1:
        return t_dims[0]
    if len(t_dims) > 1:
        raise ValueError(
            f"Multiple time dimensions detected via CF metadata: {t_dims}"
        )

    for dim in obj.dims:
        if dim in _TIME_NAMES:
            return dim
    return None


def non_spatial_dims(obj: xr.DataArray, y_dim: str, x_dim: str) -> List[str]:
    """Return dims other than the spatial pair, preserving original order.

    Time and vertical (Z) axes are included here so they are processed
    slice-by-slice by the fill routines.
    """
    return [d for d in obj.dims if d not in (y_dim, x_dim)]


def describe_axes(obj: xr.DataArray) -> dict:
    """Return a diagnostic mapping of dim → CF role for debugging.

    Returns
    -------
    dict
        Keys: ``dims`` (role per dim), ``y``, ``x``, ``time``.
    """
    y, x = find_spatial_dims(obj)
    return {
        "dims": _roles_for_dims(obj),
        "y": y,
        "x": x,
        "time": find_time_dim(obj),
    }
