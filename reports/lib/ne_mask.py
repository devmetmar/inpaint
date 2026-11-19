"""Natural Earth 10m land mask + coastline GeoJSON for report overlays."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import xarray as xr
from affine import Affine
from cartopy.io.shapereader import natural_earth
from scipy.ndimage import binary_erosion

try:
    import geopandas as gpd
    from rasterio import features as rio_features
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "geopandas and rasterio are required for NE land masking"
    ) from exc


def _grid_affine(lon: np.ndarray, lat: np.ndarray) -> Affine:
    dx = float(lon[1] - lon[0])
    dy = float(lat[1] - lat[0])
    return Affine(dx, 0.0, float(lon[0]) - dx / 2.0, 0.0, dy, float(lat[0]) - dy / 2.0)


def _ne_land_clipped(lon: np.ndarray, lat: np.ndarray) -> "gpd.GeoDataFrame":
    shp = natural_earth(resolution="10m", category="physical", name="land")
    gdf = gpd.read_file(shp)
    return gdf.cx[float(lon.min()) : float(lon.max()), float(lat.min()) : float(lat.max())]


def land_mask_ne10m(
    lon: np.ndarray,
    lat: np.ndarray,
    land_erode_pixels: int = 1,
) -> np.ndarray:
    """Return boolean land mask on (lat, lon) grid (True = land after optional erode).

    Erosion shrinks land so a thin coastal strip of model-ocean stays unmasked
    (same idea as ``gaussian_kernel_smoothing.ipynb``).
    """
    lon = np.asarray(lon)
    lat = np.asarray(lat)
    ny, nx = len(lat), len(lon)
    gdf = _ne_land_clipped(lon, lat)
    transform = _grid_affine(lon, lat)
    shapes = [
        (geom, 1)
        for geom in gdf.geometry
        if geom is not None and not geom.is_empty
    ]
    if not shapes:
        return np.zeros((ny, nx), dtype=bool)

    raster = rio_features.rasterize(
        shapes=shapes,
        out_shape=(ny, nx),
        transform=transform,
        fill=0,
        dtype=np.uint8,
    )
    is_land = raster == 1
    if land_erode_pixels > 0:
        is_land = binary_erosion(is_land, iterations=int(land_erode_pixels))
    return is_land


def apply_ocean_mask(data: np.ndarray, is_land: np.ndarray) -> np.ndarray:
    """Set land cells to NaN; preserve ocean (including previously filled)."""
    out = np.asarray(data, dtype=np.float32).copy()
    out[is_land] = np.nan
    return out


def ne_coast_geojson(
    lon: np.ndarray,
    lat: np.ndarray,
    simplify_tol: float = 0.0,
) -> Dict[str, Any]:
    """NE 10m land boundaries clipped to bbox as GeoJSON (lon/lat WGS84).

    By default ``simplify_tol=0`` keeps the Natural Earth 10m geometry
    unmodified (only clip + boundary extraction). Set a positive tolerance
    only if you explicitly want Douglas–Peucker simplification.
    """
    from shapely.geometry import box, mapping
    from shapely.ops import unary_union

    lon = np.asarray(lon)
    lat = np.asarray(lat)
    gdf = _ne_land_clipped(lon, lat)
    if gdf.empty:
        return {"type": "FeatureCollection", "features": []}
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)

    # Clip to region bbox (keeps full NE 10m detail inside; drops exterior verts)
    pad = 0.05
    bbox = box(
        float(lon.min()) - pad,
        float(lat.min()) - pad,
        float(lon.max()) + pad,
        float(lat.max()) + pad,
    )
    geom = unary_union(gdf.geometry.values).intersection(bbox)
    if geom.is_empty:
        return {"type": "FeatureCollection", "features": []}
    boundary = geom.boundary
    if simplify_tol and simplify_tol > 0:
        boundary = boundary.simplify(simplify_tol, preserve_topology=True)

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"source": "ne10m", "simplified": bool(simplify_tol and simplify_tol > 0)},
                "geometry": mapping(boundary),
            }
        ],
    }
