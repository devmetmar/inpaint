"""PNG overlays (RGBA, transparent NaN) for Leaflet ImageOverlay."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from matplotlib import colormaps
from matplotlib.colors import Normalize
from PIL import Image


def _rgba_from_array(
    data: np.ndarray,
    cmap_name: str,
    vmin: float,
    vmax: float,
    mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Map 2-D array to uint8 RGBA; transparent where mask/NaN."""
    arr = np.asarray(data, dtype=np.float64)
    if mask is None:
        mask = ~np.isfinite(arr)
    else:
        mask = np.asarray(mask, dtype=bool) | ~np.isfinite(arr)

    norm = Normalize(vmin=vmin, vmax=vmax, clip=True)
    cmap = colormaps[cmap_name]
    rgba = cmap(norm(np.where(mask, vmin, arr)))
    rgba = (rgba * 255).astype(np.uint8)
    rgba[mask, 3] = 0
    return rgba


def array_to_overlay_png(
    data: np.ndarray,
    path: Path,
    vmin: float,
    vmax: float,
    cmap: str = "viridis",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba = _rgba_from_array(data, cmap, vmin, vmax)
    # Leaflet ImageOverlay expects north-up; if lat ascending, flip vertically
    Image.fromarray(rgba, mode="RGBA").save(path)
    return path


def mask_to_overlay_png(mask: np.ndarray, path: Path) -> Path:
    """Boolean mask → gray overlay (True visible)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    m = np.asarray(mask, dtype=bool)
    rgba = np.zeros(m.shape + (4,), dtype=np.uint8)
    rgba[m] = (40, 40, 40, 180)
    Image.fromarray(rgba, mode="RGBA").save(path)
    return path


def diff_to_overlay_png(
    diff: np.ndarray,
    path: Path,
    vabs: Optional[float] = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    d = np.asarray(diff, dtype=np.float64)
    if vabs is None or not np.isfinite(vabs) or vabs <= 0:
        finite = d[np.isfinite(d)]
        vabs = float(np.nanpercentile(np.abs(finite), 98)) if finite.size else 1.0
        if vabs == 0:
            vabs = 1e-6
    rgba = _rgba_from_array(d, "RdBu_r", -vabs, vabs)
    Image.fromarray(rgba, mode="RGBA").save(path)
    return path


def leaflet_bounds(lon: np.ndarray, lat: np.ndarray) -> Tuple[list, bool]:
    """Return Leaflet bounds [[south, west], [north, east]] and whether image was flipped.

    If latitude is ascending (south→north in array row 0 = south), Leaflet still
    expects the image top = north, so callers should flip the PNG vertically.
    """
    lon = np.asarray(lon)
    lat = np.asarray(lat)
    south, north = float(np.min(lat)), float(np.max(lat))
    west, east = float(np.min(lon)), float(np.max(lon))
    flip_ud = bool(lat[0] < lat[-1])  # row0 is south → need flip for north-up PNG
    return [[south, west], [north, east]], flip_ud


def maybe_flip_for_leaflet(data: np.ndarray, flip_ud: bool) -> np.ndarray:
    return np.flipud(data) if flip_ud else data
