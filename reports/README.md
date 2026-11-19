# Coastal fill report

Generates a comprehensive comparison of InaCAWO coastal NaN fill:

- Wave `hs`
- Flows `u`, `v` at `depth=0`
- Methods: raw · gaussian · iterative · gaussian + Natural Earth 10m land crop
- Domains: Indonesia + Selat Sunda, Nusa Tenggara, Bali, Selat Malaka, Maluku

## Outputs

| File | Description |
|------|-------------|
| [`REPORT.md`](REPORT.md) | Narrative + metrics tables + preview images |
| [`index.html`](index.html) | Leaflet map (region/variable/layer switcher) |
| `assets/` | PNG overlays + `metrics.json` |

## Regenerate

```bash
conda activate ofscawo
cd /path/to/pkgs/inpaint/reports
python generate_report.py \
  --wave /scratch/bmkg_opn/Production_Unit/CAWO_OUTPUTS/Combined/2026/11/InaCAWOWave_20261118_1200.nc \
  --flow /scratch/bmkg_opn/Production_Unit/CAWO_OUTPUTS/Combined/2026/11/InaCAWOFlows_20261118_1200.nc \
  --time-index 0
```

Or from the notebook [`../ipynb/coastal_fill_report.ipynb`](../ipynb/coastal_fill_report.ipynb).

Serve locally (recommended so GeoJSON/PNG paths resolve cleanly):

```bash
cd /path/to/pkgs/inpaint/reports
python -m http.server 8765
# open http://127.0.0.1:8765/index.html
```

OSM tiles + Leaflet CDN need network.

## Future coastlines

HTML payload includes empty `other_coastlines` GeoJSON per region. Add BMKG hires or other shorelines there for side-by-side vector comparison with NE 10m.
