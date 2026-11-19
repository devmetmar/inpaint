"""Build self-contained Leaflet HTML report (CDN Leaflet)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def build_index_html(
    out_path: Path,
    regions_payload: List[Dict[str, Any]],
    title: str = "InaCAWO Coastal Fill Report",
) -> Path:
    """Write index.html with improved UI/UX for fill comparison + coast overlays."""
    out_path = Path(out_path)
    data_json = json.dumps(regions_payload, separators=(",", ":"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    :root {{
      --bg: #0b1017;
      --panel: #141c27;
      --panel2: #1b2533;
      --text: #e8eef6;
      --muted: #8b9bb0;
      --accent: #4aa3ff;
      --accent2: #3ecf8e;
      --warn: #e8a54b;
      --danger: #e85d5d;
      --border: #2a3545;
      --radius: 10px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      padding: 14px 20px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, #182131 0%, var(--panel) 100%);
      display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: baseline;
    }}
    header h1 {{ font-size: 1.15rem; margin: 0; font-weight: 650; letter-spacing: -0.02em; }}
    header .meta {{ color: var(--muted); font-size: 0.82rem; }}
    #layout {{
      display: grid;
      grid-template-columns: minmax(300px, 360px) 1fr;
      height: calc(100vh - 62px);
    }}
    #sidebar {{
      overflow: auto;
      padding: 16px;
      border-right: 1px solid var(--border);
      background: var(--panel);
    }}
    #map-wrap {{ position: relative; min-height: 0; }}
    #map {{ height: 100%; width: 100%; background: #0a1220; }}
    /* Sharp model grid — no bilinear blur on ImageOverlay */
    .leaflet-image-layer,
    .leaflet-overlay-pane img.leaflet-image-layer {{
      image-rendering: -moz-crisp-edges;
      image-rendering: crisp-edges;
      image-rendering: pixelated;
      -ms-interpolation-mode: nearest-neighbor;
    }}
    .section {{
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--border);
    }}
    .section:first-of-type {{ margin-top: 0; padding-top: 0; border-top: none; }}
    .section-title {{
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin: 0 0 8px;
      font-weight: 600;
    }}
    label.field {{
      display: block;
      font-size: 0.72rem;
      color: var(--muted);
      margin: 0 0 5px;
    }}
    select {{
      width: 100%;
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 9px 10px;
      border-radius: 8px;
      margin-bottom: 10px;
    }}
    .hint {{
      font-size: 0.72rem;
      color: var(--muted);
      line-height: 1.45;
      margin: 0 0 10px;
    }}
    .hint.warn {{
      color: #d9b07a;
      background: rgba(232, 165, 75, 0.08);
      border: 1px solid rgba(232, 165, 75, 0.25);
      padding: 8px 10px;
      border-radius: 8px;
    }}
    .layer-btns {{ display: flex; flex-direction: column; gap: 6px; }}
    .layer-btns button {{
      text-align: left;
      padding: 9px 11px;
      border-radius: 8px;
      cursor: pointer;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
      font-size: 0.84rem;
    }}
    .layer-btns button .sub {{
      display: block;
      font-size: 0.68rem;
      color: var(--muted);
      margin-top: 2px;
    }}
    .layer-btns button.active {{
      border-color: var(--accent);
      background: #1e2f45;
      box-shadow: inset 3px 0 0 var(--accent);
    }}
    .toggle-row {{
      display: flex; align-items: flex-start; gap: 10px;
      padding: 9px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--bg);
      margin-bottom: 6px;
    }}
    .toggle-row input {{ margin-top: 3px; }}
    .toggle-row .lbl {{ font-size: 0.84rem; }}
    .toggle-row .sub {{
      display: block;
      font-size: 0.68rem;
      color: var(--muted);
      margin-top: 2px;
      line-height: 1.35;
    }}
    .swatch {{
      display: inline-block;
      width: 12px; height: 12px;
      border-radius: 2px;
      margin-right: 6px;
      vertical-align: -1px;
    }}
    .swatch.ne {{ background: var(--danger); }}
    .swatch.other {{ background: var(--warn); border: 1px dashed #000; }}
    input[type=range] {{ width: 100%; accent-color: var(--accent); }}
    .card {{
      margin-top: 4px;
      padding: 12px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--panel2);
      font-size: 0.82rem;
    }}
    .card h3 {{ margin: 0 0 8px; font-size: 0.88rem; }}
    .card table {{ width: 100%; border-collapse: collapse; }}
    .card td {{ padding: 4px 0; color: var(--muted); border-bottom: 1px solid rgba(42,53,69,0.6); }}
    .card td:last-child {{ text-align: right; color: var(--text); font-variant-numeric: tabular-nums; }}
    .status {{
      position: absolute;
      left: 12px; bottom: 12px; z-index: 1000;
      background: rgba(20, 28, 39, 0.92);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 0.75rem;
      color: var(--text);
      max-width: min(420px, 70vw);
      pointer-events: none;
    }}
    .status strong {{ color: var(--accent2); }}
    .legend {{
      position: absolute;
      right: 12px; bottom: 12px; z-index: 1000;
      background: rgba(20, 28, 39, 0.92);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 0.7rem;
      color: var(--muted);
      min-width: 140px;
    }}
    .legend .bar {{
      height: 10px; border-radius: 3px; margin: 6px 0 4px;
      background: linear-gradient(90deg, #440154, #21918c, #fde725);
    }}
    .legend .bar.diverging {{
      background: linear-gradient(90deg, #2166ac, #f7f7f7, #b2182b);
    }}
    .legend .ends {{ display: flex; justify-content: space-between; }}
    a {{ color: var(--accent); }}
    @media (max-width: 900px) {{
      #layout {{ grid-template-columns: 1fr; grid-template-rows: auto 55vh; }}
      #sidebar {{ border-right: none; border-bottom: 1px solid var(--border); max-height: 42vh; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <span class="meta">Coastal fill comparison · hs / u / v@depth=0 · gaussian vs iterative vs NE crop</span>
  </header>
  <div id="layout">
    <aside id="sidebar">
      <div class="section">
        <p class="section-title">Region &amp; variable</p>
        <label class="field" for="regionSelect">Region</label>
        <select id="regionSelect"></select>
        <label class="field" for="varSelect">Variable</label>
        <select id="varSelect">
          <option value="hs">hs — significant wave height</option>
          <option value="u">u — eastward current (depth=0)</option>
          <option value="v">v — northward current (depth=0)</option>
        </select>
      </div>

      <div class="section">
        <p class="section-title">Raster layer (pick one)</p>
        <p class="hint">Compare raw vs filled fields. <strong>+ NE crop</strong> layers mask land after fill (gaussian or iterative).</p>
        <div class="layer-btns" id="layerBtns"></div>
        <label class="field" for="opacity" style="margin-top:10px">Overlay opacity</label>
        <input id="opacity" type="range" min="0" max="100" value="80" />
      </div>

      <div class="section">
        <p class="section-title">Coastline (vector)</p>
        <p class="hint warn">
          The <span class="swatch ne"></span><strong>red</strong> line is Natural Earth 10m
          (coarse global reference — not an operational Indonesian shoreline).
          Enable a hires source (e.g. BMKG) when hooked for a representative coastal check.
        </p>
        <div class="toggle-row">
          <input type="checkbox" id="toggleNe" />
          <div>
            <div class="lbl"><span class="swatch ne"></span>Natural Earth 10m</div>
            <span class="sub">Off by default. Full NE 10m geometry (no simplify) — still a global-resolution product, not an operational Indonesian shoreline.</span>
          </div>
        </div>
        <div class="toggle-row">
          <input type="checkbox" id="toggleOther" disabled />
          <div>
            <div class="lbl"><span class="swatch other"></span>Other coastline (BMKG hires / …)</div>
            <span class="sub" id="otherCoastHint">Not configured — set <code>other_coastlines_url</code> per region.</span>
          </div>
        </div>
      </div>

      <div class="section">
        <p class="section-title">Region metrics</p>
        <div class="card" id="metricsCard">
          <div id="metricsBody">Loading…</div>
        </div>
        <p class="hint" style="margin-top:10px">
          Docs: <a href="REPORT.md">REPORT.md</a> ·
          Serve: <code>python -m http.server 8765</code>
        </p>
      </div>
    </aside>
    <div id="map-wrap">
      <div id="map"></div>
      <div class="status" id="statusBar">Loading map…</div>
      <div class="legend" id="legendBox">
        <div id="legendTitle">Color scale</div>
        <div class="bar" id="legendBar"></div>
        <div class="ends"><span id="legendMin">low</span><span id="legendMax">high</span></div>
      </div>
    </div>
  </div>

  <script>
    const REPORT = {data_json};

    const LAYER_KEYS = [
      ["raw", "Raw (InaCAWO)", "Original model values — NaNs on land & coastal gaps"],
      ["gaussian", "Gaussian fill", "Local NaN fill (Astropy kernel), including land"],
      ["iterative", "Iterative fill", "Laplace diffusion (global-mean seed), including land"],
      ["gaussian_ne", "Gaussian + NE 10m crop", "Fill then mask NE land"],
      ["iterative_ne", "Iterative + NE 10m crop", "Iterative fill then mask NE land"],
      ["nan_mask", "Raw NaN mask", "Black = missing cells in the original field"],
      ["diff_gauss_iter", "Δ Gaussian − Iterative", "Method difference before land crop"],
      ["diff_gauss_iter_ne", "Δ Gauss−Iter (after NE crop)", "Difference over ocean only after crop"],
    ];

    const map = L.map("map", {{ zoomControl: true, attributionControl: true }});
    // Free tiles — no API key required (avoid Carto/Mapbox keyed endpoints)
    const osm = L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 14,
      attribution: "&copy; OpenStreetMap contributors",
    }}).addTo(map);
    const esriLite = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}",
      {{ maxZoom: 14, attribution: "Tiles &copy; Esri" }}
    );
    const esriImagery = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
      {{ maxZoom: 14, attribution: "Tiles &copy; Esri" }}
    );
    L.control.layers(
      {{
        "OpenStreetMap": osm,
        "Esri Light Gray": esriLite,
        "Esri Imagery": esriImagery,
      }},
      {{}},
      {{ position: "topright" }}
    ).addTo(map);

    let imageLayer = null;
    let coastLayer = null;
    let otherCoastLayer = null;
    let activeLayerKey = "gaussian_ne";
    let neCache = {{}};
    let otherCache = {{}};

    const regionSelect = document.getElementById("regionSelect");
    const varSelect = document.getElementById("varSelect");
    const opacityInput = document.getElementById("opacity");
    const layerBtns = document.getElementById("layerBtns");
    const metricsBody = document.getElementById("metricsBody");
    const statusBar = document.getElementById("statusBar");
    const toggleNe = document.getElementById("toggleNe");
    const toggleOther = document.getElementById("toggleOther");
    const otherCoastHint = document.getElementById("otherCoastHint");

    REPORT.forEach((r, i) => {{
      const opt = document.createElement("option");
      opt.value = r.id;
      opt.textContent = r.name;
      if (i === 0) opt.selected = true;
      regionSelect.appendChild(opt);
    }});

    LAYER_KEYS.forEach(([key, label, sub]) => {{
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.key = key;
      btn.innerHTML = label + '<span class="sub">' + sub + "</span>";
      if (key === activeLayerKey) btn.classList.add("active");
      btn.addEventListener("click", () => {{
        activeLayerKey = key;
        [...layerBtns.children].forEach(b => b.classList.toggle("active", b.dataset.key === key));
        refreshOverlay();
      }});
      layerBtns.appendChild(btn);
    }});

    function currentRegion() {{
      return REPORT.find(r => r.id === regionSelect.value) || REPORT[0];
    }}

    function layerLabel(key) {{
      const hit = LAYER_KEYS.find(x => x[0] === key);
      return hit ? hit[1] : key;
    }}

    function updateLegend(entry, key) {{
      const bar = document.getElementById("legendBar");
      const title = document.getElementById("legendTitle");
      const lo = document.getElementById("legendMin");
      const hi = document.getElementById("legendMax");
      if (key === "nan_mask") {{
        title.textContent = "NaN mask";
        bar.className = "bar";
        bar.style.background = "linear-gradient(90deg,#111,#888)";
        lo.textContent = "valid";
        hi.textContent = "missing";
        return;
      }}
      if (key === "diff_gauss_iter" || key === "diff_gauss_iter_ne") {{
        title.textContent = key.endsWith("_ne") ? "Δ after NE crop" : "Δ before crop";
        bar.className = "bar diverging";
        lo.textContent = "iter >";
        hi.textContent = "< gauss";
        return;
      }}
      title.textContent = "Field value";
      bar.className = varSelect.value === "hs" ? "bar" : "bar diverging";
      if (varSelect.value === "hs") {{
        bar.style.background = "";
        lo.textContent = (entry.vmin ?? 0).toFixed(2);
        hi.textContent = (entry.vmax ?? 1).toFixed(2);
      }} else {{
        const a = Math.abs(entry.vmax ?? 1);
        lo.textContent = (-a).toFixed(2);
        hi.textContent = a.toFixed(2);
      }}
    }}

    function refreshMetrics() {{
      const r = currentRegion();
      const v = varSelect.value;
      const m = (r.metrics && r.metrics[v]) || null;
      if (!m) {{ metricsBody.innerHTML = "<em>No metrics</em>"; return; }}
      metricsBody.innerHTML = `
        <table>
          <tr><td>NaN raw</td><td>${{m.nan_raw.toLocaleString()}}</td></tr>
          <tr><td>NaN after Gaussian+NE</td><td>${{m.nan_gaussian_ne.toLocaleString()}}</td></tr>
          <tr><td>NaN after Iterative+NE</td><td>${{(m.nan_iterative_ne ?? m.nan_gaussian_ne).toLocaleString()}}</td></tr>
          <tr><td>Coastal-gain (gaussian+NE)</td><td>${{m.coastal_gain.toLocaleString()}}</td></tr>
          <tr><td>Coastal-gain (iterative+NE)</td><td>${{(m.coastal_gain_iterative ?? m.coastal_gain).toLocaleString()}}</td></tr>
          <tr><td>|Δ| gauss−iter mean (hole)</td><td>${{m.diff_mean.toFixed(4)}}</td></tr>
          <tr><td>|Δ| after NE crop mean</td><td>${{(m.diff_ne_mean ?? 0).toFixed(4)}}</td></tr>
          <tr><td>Gaussian time (s)</td><td>${{m.t_gaussian.toFixed(2)}}</td></tr>
          <tr><td>Iterative time (s)</td><td>${{m.t_iterative.toFixed(2)}}</td></tr>
        </table>`;
    }}

    async function loadGeoJSON(url, cache, key) {{
      if (!url) return null;
      if (cache[key]) return cache[key];
      try {{
        const res = await fetch(url);
        if (!res.ok) return null;
        const gj = await res.json();
        cache[key] = gj;
        return gj;
      }} catch (e) {{
        console.warn("GeoJSON fetch failed", url, e);
        return null;
      }}
    }}

    async function refreshCoast() {{
      const r = currentRegion();
      if (coastLayer) {{ map.removeLayer(coastLayer); coastLayer = null; }}
      if (otherCoastLayer) {{ map.removeLayer(otherCoastLayer); otherCoastLayer = null; }}

      if (toggleNe.checked) {{
        const ne = await loadGeoJSON(r.ne_coast_url, neCache, r.id);
        if (ne) {{
          coastLayer = L.geoJSON(ne, {{
            style: {{ color: "#e85d5d", weight: 1.4, opacity: 0.85 }},
            interactive: false,
          }}).addTo(map);
        }}
      }}

      const hasOther = Boolean(r.other_coastlines_url);
      toggleOther.disabled = !hasOther;
      otherCoastHint.textContent = hasOther
        ? "Alternate source (e.g. BMKG hires) — compare against NE."
        : "Not configured — set other_coastlines_url per region for a representative shoreline.";

      if (toggleOther.checked && hasOther) {{
        const other = await loadGeoJSON(r.other_coastlines_url, otherCache, r.id);
        if (other) {{
          otherCoastLayer = L.geoJSON(other, {{
            style: {{ color: "#e8a54b", weight: 1.6, opacity: 0.95, dashArray: "5 3" }},
            interactive: false,
          }}).addTo(map);
        }}
      }}
    }}

    async function refreshOverlay() {{
      const r = currentRegion();
      const v = varSelect.value;
      const entry = r.layers[v];
      if (!entry) return;

      const bounds = entry.bounds;
      map.fitBounds(bounds, {{ padding: [24, 24] }});

      if (imageLayer) {{ map.removeLayer(imageLayer); imageLayer = null; }}
      const url = entry.overlays[activeLayerKey];
      if (url) {{
        imageLayer = L.imageOverlay(url, bounds, {{
          opacity: opacityInput.value / 100,
          interactive: false,
        }}).addTo(map);
      }}

      updateLegend(entry, activeLayerKey);
      statusBar.innerHTML = `<strong>${{r.name}}</strong> · ${{v}} · ${{layerLabel(activeLayerKey)}}`;
      refreshMetrics();
      await refreshCoast();
    }}

    regionSelect.addEventListener("change", () => refreshOverlay());
    varSelect.addEventListener("change", () => refreshOverlay());
    opacityInput.addEventListener("input", () => {{
      if (imageLayer) imageLayer.setOpacity(opacityInput.value / 100);
    }});
    toggleNe.addEventListener("change", () => refreshCoast());
    toggleOther.addEventListener("change", () => refreshCoast());

    refreshOverlay();
  </script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path
