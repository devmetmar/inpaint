"""Render REPORT.md from metrics + asset paths."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def build_report_md(
    out_path: Path,
    meta: Dict[str, Any],
    regions: List[Dict[str, Any]],
) -> Path:
    lines: List[str] = []
    lines.append("# InaCAWO Coastal Fill Report")
    lines.append("")
    lines.append(f"_Generated {meta.get('generated_at', '')}_")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append(
        "Compare coastal NaN extrapolation for InaCAWO Wave and Flows near "
        "coastlines: **raw** vs **gaussian** vs **iterative**, then "
        "**gaussian + Natural Earth 10m land crop** so only ocean / nearshore "
        "cells remain. Interactive maps: [`index.html`](index.html)."
    )
    lines.append("")
    lines.append("## Data")
    lines.append("")
    lines.append(f"- Wave: `{meta.get('wave_path')}`")
    lines.append(f"- Flow: `{meta.get('flow_path')}`")
    lines.append(f"- Time index: `{meta.get('time_index')}`")
    lines.append("- Variables: `hs` (wave); `u`, `v` at `depth=0` (flows)")
    lines.append("")
    lines.append("## Methods")
    lines.append("")
    lines.append("| Step | Detail |")
    lines.append("|------|--------|")
    lines.append("| Gaussian | `inpaint.fill_nans(..., method='gaussian', stddev=1.0)` |")
    lines.append(
        "| Iterative | `method='iterative', max_iter=200, tol=1e-4` "
        "(seed = global nanmean, then 3×3 diffusion) |"
    )
    lines.append(
        "| Land crop | Natural Earth **10m** land rasterized to model grid; "
        "`binary_erosion` iterations = 1; land → NaN |"
    )
    lines.append(
        "| Coastal-gain | Cells that are NaN in raw, ocean after NE mask, "
        "and finite after gaussian+NE |"
    )
    lines.append("")
    lines.append("## Regions")
    lines.append("")
    lines.append("| ID | Name | Lon | Lat | Stride |")
    lines.append("|----|------|-----|-----|--------|")
    for r in regions:
        b = r["bbox"]
        lines.append(
            f"| `{r['id']}` | {r['name']} | "
            f"{b['lon_min']}–{b['lon_max']} | "
            f"{b['lat_min']}–{b['lat_max']} | {r.get('stride', 1)} |"
        )
    lines.append("")
    lines.append("## Interactive map")
    lines.append("")
    lines.append(
        "Open [`index.html`](index.html) (requires network for OSM + Leaflet CDN). "
        "Use region / variable selectors and layer buttons. NE 10m coastline is "
        "drawn as a vector overlay; `other_coastlines` is reserved for future "
        "BMKG hires or alternative shorelines."
    )
    lines.append("")
    lines.append("## Metrics")
    lines.append("")

    for r in regions:
        lines.append(f"### {r['name']} (`{r['id']}`)")
        lines.append("")
        lines.append(
            "| Var | NaN raw | NaN G+NE | NaN I+NE | Gain G | Gain I | "
            "|Δ| hole | |Δ| NE | t_g | t_i |"
        )
        lines.append(
            "|-----|---------|----------|----------|--------|--------|"
            "---------|-------|-----|-----|"
        )
        for var in ("hs", "u", "v"):
            m = r.get("metrics", {}).get(var)
            if not m:
                continue
            lines.append(
                f"| `{var}` | {m['nan_raw']:,} | {m['nan_gaussian_ne']:,} | "
                f"{m.get('nan_iterative_ne', m['nan_gaussian_ne']):,} | "
                f"{m['coastal_gain']:,} | {m.get('coastal_gain_iterative', m['coastal_gain']):,} | "
                f"{m['diff_mean']:.4f} | {m.get('diff_ne_mean', 0):.4f} | "
                f"{m['t_gaussian']:.2f} | {m['t_iterative']:.2f} |"
            )
        lines.append("")
        # Static preview: gaussian_ne for hs if present
        preview = r.get("preview_png")
        if preview:
            lines.append(f"![preview {r['id']}]({preview})")
            lines.append("")

    lines.append("## Notes / next steps")
    lines.append("")
    lines.append(
        "- Prefer **gaussian + NE crop** for operational coastal fill; "
        "iterative is shown for method contrast (can over-diffuse into land holes "
        "before masking)."
    )
    lines.append(
        "- Next coastline comparison: add BMKG `land_mask_hires` (or other) into "
        "`other_coastlines` GeoJSON in the HTML payload without changing the fill API."
    )
    lines.append(
        "- Regenerate: `python generate_report.py` from this directory (env `ofscawo`)."
    )
    lines.append("")

    out_path = Path(out_path)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
