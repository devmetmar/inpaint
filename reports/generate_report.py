#!/usr/bin/env python3
"""Generate coastal-fill report: assets + REPORT.md + index.html.

Example
-------
conda activate ofscawo
cd pkgs/inpaint/reports
python generate_report.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xarray as xr
import yaml

# Allow running without installing reports as a package
REPORTS_DIR = Path(__file__).resolve().parent
PKG_ROOT = REPORTS_DIR.parent
sys.path.insert(0, str(REPORTS_DIR))

from lib.html_report import build_index_html
from lib.markdown_report import build_report_md
from lib.ne_mask import apply_ocean_mask, land_mask_ne10m, ne_coast_geojson
from lib.rasters import (
    array_to_overlay_png,
    diff_to_overlay_png,
    leaflet_bounds,
    mask_to_overlay_png,
    maybe_flip_for_leaflet,
)

from inpaint import fill_nans

DEFAULT_WAVE = (
    "/scratch/bmkg_opn/Production_Unit/CAWO_OUTPUTS/Combined/"
    "2026/11/InaCAWOWave_20261118_1200.nc"
)
DEFAULT_FLOW = (
    "/scratch/bmkg_opn/Production_Unit/CAWO_OUTPUTS/Combined/"
    "2026/11/InaCAWOFlows_20261118_1200.nc"
)


def load_regions(path: Path) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return list(raw["regions"])


def _subset_da(da: xr.DataArray, lon_slice, lat_slice, stride: int) -> xr.DataArray:
    out = da.sel(lon=lon_slice, lat=lat_slice)
    if stride > 1:
        out = out.isel(lat=slice(None, None, stride), lon=slice(None, None, stride))
    return out.load()


def _vmin_vmax(da: xr.DataArray, var: str) -> Tuple[float, float]:
    vals = da.values[np.isfinite(da.values)]
    if vals.size == 0:
        return 0.0, 1.0
    if var == "hs":
        return 0.0, float(np.nanpercentile(vals, 98))
    lim = float(np.nanpercentile(np.abs(vals), 98))
    lim = lim if lim > 0 else 1.0
    return -lim, lim


def _metrics(
    raw: np.ndarray,
    gauss: np.ndarray,
    itera: np.ndarray,
    gauss_ne: np.ndarray,
    itera_ne: np.ndarray,
    is_land: np.ndarray,
    t_g: float,
    t_i: float,
) -> Dict[str, Any]:
    raw_nan = ~np.isfinite(raw)
    ocean = ~is_land
    coastal_gain = int((raw_nan & ocean & np.isfinite(gauss_ne)).sum())
    coastal_gain_iter = int((raw_nan & ocean & np.isfinite(itera_ne)).sum())
    hole = raw_nan & np.isfinite(gauss) & np.isfinite(itera)
    if hole.any():
        d = np.abs(gauss[hole] - itera[hole])
        diff_mean = float(np.mean(d))
        diff_max = float(np.max(d))
    else:
        diff_mean = 0.0
        diff_max = 0.0
    # Difference on ocean cells after both NE crops
    both_ne = np.isfinite(gauss_ne) & np.isfinite(itera_ne)
    if both_ne.any():
        d_ne = np.abs(gauss_ne[both_ne] - itera_ne[both_ne])
        diff_ne_mean = float(np.mean(d_ne))
        diff_ne_max = float(np.max(d_ne))
    else:
        diff_ne_mean = 0.0
        diff_ne_max = 0.0
    return {
        "nan_raw": int(raw_nan.sum()),
        "nan_gaussian_ne": int((~np.isfinite(gauss_ne)).sum()),
        "nan_iterative_ne": int((~np.isfinite(itera_ne)).sum()),
        "coastal_gain": coastal_gain,
        "coastal_gain_iterative": coastal_gain_iter,
        "diff_mean": diff_mean,
        "diff_max": diff_max,
        "diff_ne_mean": diff_ne_mean,
        "diff_ne_max": diff_ne_max,
        "t_gaussian": t_g,
        "t_iterative": t_i,
    }


def _process_field(
    da: xr.DataArray,
    var: str,
    region_id: str,
    assets_dir: Path,
    land_erode_pixels: int,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
    """Fill, mask, write overlays; return (overlays meta, metrics, preview relpath)."""
    lon = da["lon"].values
    lat = da["lat"].values
    bounds, flip_ud = leaflet_bounds(lon, lat)

    t0 = time.perf_counter()
    g_da = fill_nans(da, method="gaussian", stddev=1.0, parallel=False)
    t_g = time.perf_counter() - t0

    t0 = time.perf_counter()
    i_da = fill_nans(da, method="iterative", max_iter=200, tol=1e-4, parallel=False)
    t_i = time.perf_counter() - t0

    raw = np.asarray(da.values, dtype=np.float32)
    gauss = np.asarray(g_da.values, dtype=np.float32)
    itera = np.asarray(i_da.values, dtype=np.float32)

    is_land = land_mask_ne10m(lon, lat, land_erode_pixels=land_erode_pixels)
    gauss_ne = apply_ocean_mask(gauss, is_land)
    itera_ne = apply_ocean_mask(itera, is_land)

    metrics = _metrics(raw, gauss, itera, gauss_ne, itera_ne, is_land, t_g, t_i)

    vmin, vmax = _vmin_vmax(da, var)
    cmap = "viridis" if var == "hs" else "RdBu_r"
    out_dir = assets_dir / region_id / var
    out_dir.mkdir(parents=True, exist_ok=True)

    def save_data(name: str, arr: np.ndarray, **kw) -> str:
        flipped = maybe_flip_for_leaflet(arr, flip_ud)
        path = out_dir / f"{name}.png"
        if name == "nan_mask":
            mask_to_overlay_png(flipped.astype(bool), path)
        elif name in ("diff_gauss_iter", "diff_gauss_iter_ne"):
            diff_to_overlay_png(flipped, path)
        else:
            array_to_overlay_png(flipped, path, vmin=kw.get("vmin", vmin), vmax=kw.get("vmax", vmax), cmap=kw.get("cmap", cmap))
        # relative to reports/
        return f"assets/{region_id}/{var}/{name}.png"

    overlays = {
        "raw": save_data("raw", raw),
        "gaussian": save_data("gaussian", gauss),
        "iterative": save_data("iterative", itera),
        "gaussian_ne": save_data("gaussian_ne", gauss_ne),
        "iterative_ne": save_data("iterative_ne", itera_ne),
        "nan_mask": save_data("nan_mask", (~np.isfinite(raw)).astype(np.float32)),
        "diff_gauss_iter": save_data("diff_gauss_iter", gauss - itera),
        "diff_gauss_iter_ne": save_data("diff_gauss_iter_ne", gauss_ne - itera_ne),
    }

    # static preview for markdown (gaussian_ne)
    preview = overlays["gaussian_ne"] if var == "hs" else None

    layer_meta = {
        "bounds": bounds,
        "overlays": overlays,
        "vmin": vmin,
        "vmax": vmax,
    }
    return layer_meta, metrics, preview


def run(
    wave_path: Path,
    flow_path: Path,
    time_index: int = 0,
    land_erode_pixels: int = 2,
    regions_file: Optional[Path] = None,
) -> Dict[str, Any]:
    regions_file = regions_file or (REPORTS_DIR / "regions.yaml")
    assets_dir = REPORTS_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    regions_cfg = load_regions(regions_file)
    print(f"Loading wave: {wave_path}", flush=True)
    dw = xr.open_dataset(wave_path, decode_times=False)
    print(f"Loading flow: {flow_path}", flush=True)
    df = xr.open_dataset(flow_path, decode_times=False)

    hs_full = dw["hs"].isel(time=time_index)
    u_full = df["u"].isel(time=time_index).sel(depth=0)
    v_full = df["v"].isel(time=time_index).sel(depth=0)

    payload_regions: List[Dict[str, Any]] = []
    md_regions: List[Dict[str, Any]] = []

    for cfg in regions_cfg:
        rid = cfg["id"]
        name = cfg["name"]
        stride = int(cfg.get("stride", 1))
        lon_sl = slice(cfg["lon_min"], cfg["lon_max"])
        lat_sl = slice(cfg["lat_min"], cfg["lat_max"])
        print(f"\n=== Region {rid} ({name}) stride={stride} ===", flush=True)

        fields = {
            "hs": _subset_da(hs_full, lon_sl, lat_sl, stride),
            "u": _subset_da(u_full, lon_sl, lat_sl, stride),
            "v": _subset_da(v_full, lon_sl, lat_sl, stride),
        }

        layers: Dict[str, Any] = {}
        metrics: Dict[str, Any] = {}
        preview_png = None

        # NE coast from first field grid
        sample = fields["hs"]
        lon = sample["lon"].values
        lat = sample["lat"].values
        # Keep NE 10m geometry as-is (no Douglas–Peucker simplify).
        coast = ne_coast_geojson(lon, lat, simplify_tol=0.0)
        coast_path = assets_dir / rid / "ne_coast.geojson"
        coast_path.parent.mkdir(parents=True, exist_ok=True)
        coast_path.write_text(json.dumps(coast), encoding="utf-8")

        for var, da in fields.items():
            print(f"  processing {var} shape={da.shape} nan={int(da.isnull().sum()):,}", flush=True)
            layer_meta, m, preview = _process_field(
                da, var, rid, assets_dir, land_erode_pixels=land_erode_pixels
            )
            layers[var] = layer_meta
            metrics[var] = m
            if preview and preview_png is None:
                preview_png = preview
            print(
                f"    coastal_gain={m['coastal_gain']:,} "
                f"|Δ|mean={m['diff_mean']:.4f} t_g={m['t_gaussian']:.2f}s t_i={m['t_iterative']:.2f}s",
                flush=True,
            )

        payload_regions.append(
            {
                "id": rid,
                "name": name,
                "bbox": {
                    "lon_min": cfg["lon_min"],
                    "lon_max": cfg["lon_max"],
                    "lat_min": cfg["lat_min"],
                    "lat_max": cfg["lat_max"],
                },
                "stride": stride,
                "layers": layers,
                "metrics": metrics,
                # Coastline loaded at runtime via URL (keeps index.html small)
                "ne_coast_url": f"assets/{rid}/ne_coast.geojson",
                "other_coastlines_url": None,
            }
        )
        md_regions.append(
            {
                "id": rid,
                "name": name,
                "bbox": payload_regions[-1]["bbox"],
                "stride": stride,
                "metrics": metrics,
                "preview_png": preview_png,
            }
        )

    dw.close()
    df.close()

    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "wave_path": str(wave_path),
        "flow_path": str(flow_path),
        "time_index": time_index,
        "land_erode_pixels": land_erode_pixels,
    }

    metrics_path = assets_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps({"meta": meta, "regions": payload_regions}, indent=2, default=str),
        encoding="utf-8",
    )

    html_path = build_index_html(REPORTS_DIR / "index.html", payload_regions)
    md_path = build_report_md(REPORTS_DIR / "REPORT.md", meta, md_regions)

    print(f"\nWrote {html_path}", flush=True)
    print(f"Wrote {md_path}", flush=True)
    print(f"Wrote {metrics_path}", flush=True)
    return {"html": str(html_path), "md": str(md_path), "metrics": str(metrics_path)}


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Generate InaCAWO coastal fill report")
    p.add_argument("--wave", type=Path, default=Path(DEFAULT_WAVE))
    p.add_argument("--flow", type=Path, default=Path(DEFAULT_FLOW))
    p.add_argument("--time-index", type=int, default=0)
    p.add_argument("--land-erode-pixels", type=int, default=2)
    p.add_argument("--regions", type=Path, default=REPORTS_DIR / "regions.yaml")
    args = p.parse_args(argv)

    if not args.wave.exists():
        print(f"ERROR: wave file not found: {args.wave}", file=sys.stderr)
        return 1
    if not args.flow.exists():
        print(f"ERROR: flow file not found: {args.flow}", file=sys.stderr)
        return 1

    run(
        wave_path=args.wave,
        flow_path=args.flow,
        time_index=args.time_index,
        land_erode_pixels=args.land_erode_pixels,
        regions_file=args.regions,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
