#!/usr/bin/env python3
"""Convert the drone-track endpoints CSV into an interactive HTML map with a 1-hour time scrubber.

The script targets the schema produced by trackendpoints exports (UTF-8 BOM,
Ukrainian headers): each row is one track and we keep its LAST observed
position (`Час останньої фіксації` + `Координати останньої точки`).
"""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path


CSV_PATHS = [
    Path("/root/.claude/uploads/00933357-837f-4dc5-8c42-22708f358e69/2e486a91-trackendpoints0103202601042026.csv"),
    Path("/root/.claude/uploads/00933357-837f-4dc5-8c42-22708f358e69/2b738f02-trackendpoints0104202601052026_2.csv"),
    Path("/root/.claude/uploads/5554a83c-6e5b-498c-9c56-2ea45dff2711/814c6f5c-trackendpoints0105202601062026.csv"),
]
OUT_PATH = Path(__file__).parent / "drones_map.html"

COL_ID      = "Номер цілі"
COL_TIME    = "Час останньої фіксації"
COL_COORDS  = "Координати останньої точки"
COL_PLACE   = "Найближчий населений пункт"
COL_NAME    = "Назва цілі"
COL_TYPE    = "Тип цілі"
COL_TAGS    = "Теги"
COL_COMMENT = "Коментар"


def parse_rows():
    events = []
    seen = set()      # de-dup across files via (target id, last-fix timestamp)
    skipped = 0
    duped = 0
    for path in CSV_PATHS:
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                tstr = (row.get(COL_TIME) or "").strip()
                coords = (row.get(COL_COORDS) or "").strip()
                if not tstr or not coords:
                    skipped += 1
                    continue
                try:
                    ts = datetime.strptime(tstr, "%H:%M:%S %d.%m.%Y")
                except ValueError:
                    skipped += 1
                    continue
                try:
                    lat_str, lon_str = coords.split(",", 1)
                    lat = float(lat_str.strip())
                    lon = float(lon_str.strip())
                except (ValueError, IndexError):
                    skipped += 1
                    continue
                tgt_id = (row.get(COL_ID) or "").strip()
                dedup_key = (tgt_id, tstr) if tgt_id else (tstr, lat, lon)
                if dedup_key in seen:
                    duped += 1
                    continue
                seen.add(dedup_key)
                tod = ts.hour * 3600 + ts.minute * 60 + ts.second
                raw_tags = (row.get(COL_TAGS) or "").strip()
                tags = [t.strip() for t in raw_tags.replace(";", ",").split(",") if t.strip()]
                events.append({
                    "tod": tod,
                    "date": ts.strftime("%Y-%m-%d"),
                    "time": ts.strftime("%H:%M:%S"),
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "name": (row.get(COL_NAME) or "").strip(),
                    "type": (row.get(COL_TYPE) or "").strip(),
                    "tags": tags,
                    "place": (row.get(COL_PLACE) or "").strip(),
                    "comment": (row.get(COL_COMMENT) or "").strip(),
                })
    events.sort(key=lambda e: e["tod"])
    print(f"Parsed {len(events)} events (skipped {skipped}, deduped {duped}) "
          f"from {len(CSV_PATHS)} files", file=sys.stderr)
    return events


HTML_TEMPLATE = """<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<title>Хронологія БПЛА &mdash; скрабер</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&family=Geist:wght@400;500;600;700;800;900&display=swap" rel="stylesheet"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
<style>
  :root {
    --ink: #f5f5f3;
    --dim: #9a9b95;
    --dimmer: #62635d;
    --line: rgba(255,255,255,0.08);
    --accent: #ff8b3d;
    --accent-soft: rgba(255,139,61,0.13);
    --accent-2: #6db6ff;
    --bar-dim: rgba(150,160,175,0.40);
    --font-display: 'Geist', system-ui, sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, monospace;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: var(--font-display);
    color: var(--ink);
    background: #000;
    -webkit-font-smoothing: antialiased;
    overflow: hidden;
  }
  .stage { position: fixed; inset: 0; background: #000; display: flex; flex-direction: column; }

  /* Month selector inline next to the timeline title */
  .topbar-select {
    font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.04em;
    background: transparent; color: var(--ink); border: 1px solid var(--line);
    padding: 3px 6px; cursor: pointer;
  }
  .topbar-select option { background: #111; color: var(--ink); }
  .clock-inline {
    font-family: var(--font-mono); font-size: 10.5px;
    color: var(--dimmer); letter-spacing: 0.12em;
  }
  .title-row { display: flex; align-items: center; gap: 14px; }

  /* ── Map area ─────────────────────────────────────────── */
  .mapwrap { position: relative; flex: 1; min-height: 0; }
  #map { position: absolute; inset: 0; background: #000; }
  .leaflet-container { background: #000; outline: none; font-family: var(--font-mono); }
  .leaflet-control-attribution {
    background: rgba(0,0,0,0.6) !important; color: rgba(255,255,255,0.5) !important;
    font-family: var(--font-mono); font-size: 9px; padding: 2px 6px;
  }
  .leaflet-control-attribution a { color: rgba(255,255,255,0.7) !important; }
  .leaflet-control-zoom a {
    background: rgba(0,0,0,0.7) !important; color: var(--ink) !important;
    border: 1px solid var(--line) !important;
  }
  /* Leaflet.draw toolbar restyle */
  .leaflet-draw-toolbar a, .leaflet-draw-actions a {
    background-color: rgba(0,0,0,0.7) !important;
    border-color: var(--line) !important;
    color: var(--ink) !important;
  }
  .leaflet-popup-content-wrapper, .leaflet-popup-tip {
    background: #111; color: var(--ink); border: 1px solid var(--line);
    border-radius: 0; font-family: var(--font-mono); font-size: 11px;
  }
  .leaflet-popup-content b { font-family: var(--font-display); font-weight: 700; }

  /* HUD over map (top-left) */
  .hud {
    position: absolute; top: 18px; left: 18px; z-index: 500;
    background: rgba(0,0,0,0.72); border: 1px solid var(--line);
    backdrop-filter: blur(6px);
    padding: 18px 22px 20px; width: 260px;
  }
  .hud .lbl { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.18em; color: var(--dim); }
  .hud .huge {
    font-family: var(--font-display); font-weight: 600; font-size: 72px;
    line-height: 0.92; letter-spacing: -0.04em; color: var(--ink);
    font-variant-numeric: tabular-nums; margin: 8px 0 2px;
  }
  .hud .sub { font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.06em; color: var(--dim); }
  .hud .sub b { color: var(--accent); font-weight: 600; }
  .hud .hr { height: 1px; background: var(--line); margin: 16px 0 14px; }
  .hud .mini { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 10px; }
  .hud .mini:last-child { margin-bottom: 0; }
  .hud .mini .mk { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.14em; color: var(--dimmer); }
  .hud .mini .mv { font-family: var(--font-mono); font-size: 13px; color: var(--ink); font-variant-numeric: tabular-nums; }
  .hud .mini .mv.peak { color: var(--accent-2); }
  .hud .mini .mv.area { color: var(--accent); }

  /* ── Scrubber bar ─────────────────────────────────────── */
  .scrubber {
    flex: none; background: #000; border-top: 1px solid var(--line);
    padding: 14px clamp(16px, 2.4vw, 36px) 16px;
    display: flex; flex-direction: column; gap: 10px; z-index: 600;
  }
  .track-head { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; }
  .track-head .month { font-family: var(--font-display); font-weight: 700; font-size: 13px; letter-spacing: 0.16em; color: var(--ink); }
  .track-head .hint { font-family: var(--font-mono); font-size: 10.5px; color: var(--dimmer); letter-spacing: 0.1em; }

  /* Slider/histogram block (keeps existing markup, sharpened style) */
  #scrub {
    position: relative;
    height: 96px;
  }
  #hist {
    position: absolute;
    top: 0; left: 7px;
    width: calc(100% - 14px);
    height: 60px;
    background: transparent;
    display: block;
  }
  #scrub-track {
    position: absolute;
    top: 60px; left: 7px;
    width: calc(100% - 14px);
    height: 8px;
    background: rgba(255,255,255,0.05);
    border-top: 1px solid var(--line);
    overflow: hidden;
  }
  .scrub-band {
    position: absolute;
    top: 0;
    height: 68px;
    background: var(--accent-soft);
    border-left: 1px solid var(--accent);
    border-right: 1px solid var(--accent);
    box-sizing: border-box;
    pointer-events: none;
  }
  /* Slider spans the entire histogram + track band so the playhead is
     easy to grab from anywhere in the scrub area. */
  #slider {
    position: absolute;
    top: 0; left: 0; right: 0;
    width: 100%;
    margin: 0;
    -webkit-appearance: none;
    appearance: none;
    background: transparent;
    height: 72px;
    cursor: pointer;
  }
  #slider::-webkit-slider-runnable-track { background: transparent; height: 72px; border: 0; }
  #slider::-moz-range-track            { background: transparent; height: 72px; border: 0; }
  #slider::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none;
    width: 3px; height: 72px;
    background: #fff; border: 0; border-radius: 2px;
    cursor: ew-resize;
    box-shadow:
      0 0 0 1px rgba(0,0,0,0.55),
      0 0 8px rgba(255,255,255,0.55),
      0 0 18px rgba(255,255,255,0.18);
  }
  #slider::-moz-range-thumb {
    width: 3px; height: 72px;
    background: #fff; border: 0; border-radius: 2px;
    cursor: ew-resize;
    box-shadow:
      0 0 0 1px rgba(0,0,0,0.55),
      0 0 8px rgba(255,255,255,0.55),
      0 0 18px rgba(255,255,255,0.18);
  }
  #scrub-axis {
    position: absolute;
    top: 72px; left: 7px; right: 7px;
    height: 24px;
    pointer-events: none;
  }
  .scrub-tick { position: absolute; width: 1px; background: rgba(255,255,255,0.12); top: 0; transform: translateX(-0.5px); }
  .scrub-tick.major { height: 6px; background: rgba(255,255,255,0.32); }
  .scrub-tick.minor { height: 3px; }
  .scrub-label {
    position: absolute; top: 8px;
    font-family: var(--font-mono); font-size: 10px;
    color: var(--dimmer); letter-spacing: 0.08em;
    transform: translateX(-50%); white-space: nowrap;
  }

  /* Single row between title and timeline:
     filters on the left, time controls on the right. */
  .bottombar {
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    font-family: var(--font-mono);
  }
  .filter-bar, .time-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .filter-bar { flex: 1 1 auto; min-width: 0; }
  .time-bar   { flex: 0 0 auto; margin-left: auto; }
  .filter-bar .filter-lbl {
    font-size: 9.5px; letter-spacing: 0.16em;
    color: var(--dimmer); text-transform: uppercase;
    margin-right: -4px;
  }
  .filter-bar .group-sep {
    width: 1px; height: 14px; background: var(--line); margin: 0 4px;
  }

  .play {
    display: inline-flex; align-items: center; gap: 7px;
    font-family: var(--font-mono); font-weight: 600; font-size: 11px;
    letter-spacing: 0.12em; padding: 5px 14px;
    background: var(--accent); color: #1a0f06; border: 0; border-radius: 999px;
    cursor: pointer; transition: background 120ms;
  }
  .play:hover { background: #ff9d5a; }
  .play .icon { font-size: 9px; }
  .ctrl-label { font-size: 9.5px; color: var(--dimmer); letter-spacing: 0.16em; }
  .win-seg { display: flex; gap: 4px; }
  .win-seg button {
    height: 24px; padding: 0 12px;
    font-family: var(--font-mono); font-size: 10.5px; font-weight: 600; letter-spacing: 0.1em;
    line-height: 1;
    border: 1px solid var(--line); border-radius: 999px;
    background: transparent;
    color: var(--dimmer); cursor: pointer; transition: all 120ms;
  }
  .win-seg button:hover { color: var(--ink); border-color: rgba(255,255,255,0.2); }
  .win-seg button.is-active {
    background: var(--accent); border-color: var(--accent); color: #1a0f06;
  }
  .ghost-btn {
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.12em;
    background: transparent; border: 1px solid var(--line); border-radius: 999px;
    color: var(--dim);
    padding: 5px 11px; cursor: pointer; transition: all 120ms;
  }
  .ghost-btn:hover { color: var(--ink); border-color: rgba(255,255,255,0.2); }

  #areaStatus {
    display: none;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.12em;
    padding: 4px 8px;
    border: 1px solid var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
  }
  #areaStatus.active { display: inline-flex; align-items: center; gap: 8px; }
  #areaStatus a { color: var(--ink); cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }

  .readout-inline {
    font-family: var(--font-mono); font-size: 11.5px; color: var(--ink);
    letter-spacing: 0.06em; font-variant-numeric: tabular-nums;
    padding: 0 4px;
  }

  /* Filter pills — filled when active, grey when not. Same height as
     the time-frame segmented buttons. */
  #typeFilters, #tagFilters {
    display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap;
  }
  .pill {
    display: inline-flex; align-items: center;
    height: 24px; padding: 0 12px;
    border: 1px solid var(--line);
    border-radius: 999px;
    font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.06em;
    line-height: 1;
    cursor: pointer; user-select: none;
    background: transparent; color: var(--dimmer);
    transition: all 120ms;
  }
  .pill:hover { color: var(--ink); border-color: rgba(255,255,255,0.2); }
  .pill.active {
    background: var(--col, var(--accent));
    border-color: var(--col, var(--accent));
    color: #0c0c0c;
  }
  .pill.tag.active {
    background: var(--accent); border-color: var(--accent); color: #1a0f06;
  }
</style>
</head>
<body>
<div class="stage">
  <!-- Map -->
  <div class="mapwrap">
    <div id="map"></div>

    <div class="hud">
      <div class="lbl">ЗА ОБРАНИЙ ПЕРІОД</div>
      <div class="huge" id="hudBig">0</div>
      <div class="sub">з <span id="hudPool">__TOTAL__</span> · <b id="hudPct">0%</b></div>
      <div class="hr"></div>
      <div class="mini"><span class="mk">ПІК ЗА ДОБОЮ</span><span class="mv peak" id="hudPeak">0</span></div>
      <div class="mini"><span class="mk">ПІК О</span><span class="mv" id="hudPeakTime">&mdash;</span></div>
    </div>
  </div>

  <!-- Scrubber -->
  <div class="scrubber">
    <div class="track-head">
      <div class="title-row">
        <div class="month" id="scrubTitle">ХРОНОЛОГІЯ ПОДІЙ</div>
        <select class="topbar-select" id="monthSel"></select>
        <span class="clock-inline" id="clock">__DAYS__ ДНІВ · __DATE_RANGE__</span>
      </div>
      <div class="hint">ПЕРЕТЯГНІТЬ ПОВЗУНОК · ПРОБІЛ — ВІДТВОРЕННЯ · ← →  КРОК</div>
    </div>
    <div id="scrub">
      <canvas id="hist"></canvas>
      <div id="scrub-track"></div>
      <div class="scrub-band" id="band1"></div>
      <div class="scrub-band" id="band2" style="display:none"></div>
      <input id="slider" type="range" min="0" max="86340" value="43200" step="60">
      <div id="scrub-axis"></div>
    </div>
    <div class="bottombar">
      <div class="filter-bar">
        <span class="filter-lbl">ТИП</span>
        <span id="typeFilters"></span>
        <span class="group-sep"></span>
        <span class="filter-lbl">ТЕГИ</span>
        <span id="tagFilters"></span>
        <span id="areaStatus">&#9633; ОБЛАСТЬ
          <a id="clearArea">скинути</a></span>
      </div>
      <div class="time-bar">
        <span class="readout-inline" id="winRange">&mdash;</span>
        <button class="play" id="play"><span class="icon">&#9654;</span><span id="playLabel">ВІДТВОРИТИ</span></button>
        <span class="ctrl-label">ВІКНО</span>
        <div class="win-seg" id="winSeg">
          <button data-win="1800">30 ХВ</button>
          <button data-win="3600" class="is-active">1 ГОД</button>
          <button data-win="7200">2 ГОД</button>
        </div>
        <button class="ghost-btn" id="resetBtn">12:00</button>
      </div>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
<script>
const EVENTS = __DATA__;

const map = L.map('map', {
  preferCanvas: true,
  zoomControl: true,
  attributionControl: true,
});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
  maxZoom: 19,
  attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
}).addTo(map);

// Fit to all event bounds initially.
const allBounds = L.latLngBounds(EVENTS.map(e => [e.lat, e.lon]));
map.fitBounds(allBounds, { padding: [20, 20] });

const markerRenderer = L.canvas({ padding: 0.5 });
const markerLayer = L.layerGroup().addTo(map);

// --- area selection (rectangle / polygon) ---
const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);
const drawControl = new L.Control.Draw({
  position: 'topright',
  draw: {
    polyline: false,
    circle: false,
    circlemarker: false,
    marker: false,
    rectangle: { shapeOptions: { color: '#ff8b3d', weight: 2, fillOpacity: 0.05 } },
    polygon: { shapeOptions: { color: '#ff8b3d', weight: 2, fillOpacity: 0.05 },
               allowIntersection: false, showArea: false }
  },
  edit: { featureGroup: drawnItems, edit: true, remove: true }
});
map.addControl(drawControl);

let selectionPolygon = null;  // [[lat,lon], ...] or null

function pointInPolygon(lat, lon, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const yi = poly[i][0], xi = poly[i][1];
    const yj = poly[j][0], xj = poly[j][1];
    if (((yi > lat) !== (yj > lat)) &&
        (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)) {
      inside = !inside;
    }
  }
  return inside;
}

function refreshSelectionFromLayers() {
  const layers = drawnItems.getLayers();
  if (!layers.length) {
    selectionPolygon = null;
  } else {
    const layer = layers[layers.length - 1];
    let ll = layer.getLatLngs();
    while (Array.isArray(ll[0])) ll = ll[0];  // unwrap polygon ring
    selectionPolygon = ll.map(p => [p.lat, p.lng]);
  }
  document.getElementById('areaStatus').classList.toggle('active', !!selectionPolygon);
  recomputeHistBins();
  drawHistogram();
  update();
}

map.on(L.Draw.Event.CREATED, (e) => {
  drawnItems.clearLayers();          // single-shape selection
  drawnItems.addLayer(e.layer);
  refreshSelectionFromLayers();
});
map.on(L.Draw.Event.EDITED,  refreshSelectionFromLayers);
map.on(L.Draw.Event.DELETED, refreshSelectionFromLayers);
document.getElementById('clearArea').addEventListener('click', () => {
  drawnItems.clearLayers();
  refreshSelectionFromLayers();
});

// --- type / tag filters ---
const TYPE_COLORS = {
  'FPV':   '#ff8b3d',
  'Крило': '#6db6ff',
  'БПЛА':  '#a6e22e',
  '':      '#62635d',
};
const TYPE_FALLBACK_PALETTE = ['#f5d76e','#c780ff','#5be7c4','#ff7a90','#7ad7ff'];
function typeColor(t) {
  if (t in TYPE_COLORS) return TYPE_COLORS[t];
  // Assign on demand for any type beyond the built-in set.
  const i = Object.keys(TYPE_COLORS).length - 4;  // excludes the 4 built-ins
  const col = TYPE_FALLBACK_PALETTE[i % TYPE_FALLBACK_PALETTE.length];
  TYPE_COLORS[t] = col;
  return col;
}

const allTypes = [...new Set(EVENTS.map(e => e.type))]
  .sort((a, b) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)));
const allTags = [...new Set(EVENTS.flatMap(e => e.tags))].sort();

const enabledTypes = new Set(allTypes);
const enabledTags  = new Set(allTags);

function buildPillRow(host, items, enabledSet, labelFn, colorFn, extraClass, onChange) {
  host.innerHTML = '';
  for (const it of items) {
    const pill = document.createElement('span');
    pill.className = 'pill active' + (extraClass ? ' ' + extraClass : '');
    if (colorFn) pill.style.setProperty('--col', colorFn(it));
    pill.textContent = labelFn(it);
    pill.addEventListener('click', () => {
      if (enabledSet.has(it)) enabledSet.delete(it);
      else enabledSet.add(it);
      pill.classList.toggle('active', enabledSet.has(it));
      onChange();
    });
    host.appendChild(pill);
  }
}

buildPillRow(
  document.getElementById('typeFilters'),
  allTypes, enabledTypes,
  (t) => (t === '' ? 'НЕ ВИЗНАЧЕНО' : t.toUpperCase()),
  (t) => typeColor(t),
  'type',
  () => { rebuildPool(); update(); }
);
buildPillRow(
  document.getElementById('tagFilters'),
  allTags, enabledTags,
  (t) => t.replace(/^credibility:\s*/i, 'CRED · ').toUpperCase(),
  null,
  'tag',
  () => { rebuildPool(); update(); }
);

const slider = document.getElementById('slider');
const monthSel = document.getElementById('monthSel');
const playBtn = document.getElementById('play');
const playLabel = document.getElementById('playLabel');
const resetBtn = document.getElementById('resetBtn');
const band1 = document.getElementById('band1');
const band2 = document.getElementById('band2');
const axis = document.getElementById('scrub-axis');
const histCanvas = document.getElementById('hist');
const winSeg = document.getElementById('winSeg');

// Stat outputs that still exist (HUD + readout + inline clock).
const elHudBig     = document.getElementById('hudBig');
const elHudPool    = document.getElementById('hudPool');
const elHudPct     = document.getElementById('hudPct');
const elHudPeak    = document.getElementById('hudPeak');
const elHudPeakTime= document.getElementById('hudPeakTime');
const elWinRange   = document.getElementById('winRange');
const elClock      = document.getElementById('clock');

// Window-size segmented control. Read the currently active button.
function currentWindow() {
  const b = winSeg.querySelector('button.is-active');
  return b ? parseInt(b.dataset.win, 10) : 3600;
}
winSeg.addEventListener('click', (e) => {
  const b = e.target.closest('button[data-win]');
  if (!b) return;
  winSeg.querySelectorAll('button').forEach(x => x.classList.toggle('is-active', x === b));
  update();
});

// --- Month selector: "All time" plus every YYYY-MM present in data. ---
const monthSet = new Set(EVENTS.map(e => e.date.slice(0, 7)));
const months = [...monthSet].sort();
const MONTH_UA = ['СІЧ','ЛЮТ','БЕР','КВІ','ТРАВ','ЧЕР','ЛИП','СЕР','ВЕР','ЖОВ','ЛИС','ГРУ'];
function monthLabel(ym) {
  const [y, m] = ym.split('-');
  return `${MONTH_UA[parseInt(m,10)-1]} ${y}`;
}
const optAll = document.createElement('option');
optAll.value = ''; optAll.textContent = 'ВСІ МІСЯЦІ';
monthSel.appendChild(optAll);
for (const ym of months) {
  const o = document.createElement('option');
  o.value = ym; o.textContent = monthLabel(ym);
  monthSel.appendChild(o);
}

let activePool = EVENTS;   // events left after month filter
let histBins = [];         // histogram of (activePool ∩ viewport) over 24 h

// --- Sun position --------------------------------------------------------
// Mean centre of all events; the dataset lives in a small region so a
// single representative lat/lon is fine for sunrise / sunset.
const MEAN_LAT = EVENTS.reduce((s, e) => s + e.lat, 0) / EVENTS.length;
const MEAN_LON = EVENTS.reduce((s, e) => s + e.lon, 0) / EVENTS.length;

function lastSundayOfMonth(year, month /*1-12*/) {
  // Compute the day-of-month of the last Sunday.
  const last = new Date(Date.UTC(year, month, 0));     // last day of month
  return last.getUTCDate() - last.getUTCDay();
}
function isUkraineDST(y, m, d) {
  // EEST: last Sunday of March 03:00 → last Sunday of October 04:00 (local).
  if (m < 3 || m > 10) return false;
  if (m > 3 && m < 10) return true;
  const last = lastSundayOfMonth(y, m);
  return m === 3 ? d >= last : d < last;
}

// Approximate sunrise / sunset (in fractional hours local time) for a
// given Gregorian date and observer (lat, lon). Uses the simple solar
// declination model — accurate to ~2-3 min for our latitudes, which is
// plenty for a visual indicator.
function solarTimes(y, m, d, lat, lon) {
  const dayUTC = Date.UTC(y, m - 1, d);
  const N = Math.floor((dayUTC - Date.UTC(y, 0, 1)) / 86400000) + 1;
  const declRad = 23.45 * Math.PI / 180
                  * Math.sin(2 * Math.PI / 365 * (N - 81));
  const latRad = lat * Math.PI / 180;
  const cosH = -Math.tan(latRad) * Math.tan(declRad);
  if (cosH < -1 || cosH > 1) return null;
  const Hhours = Math.acos(cosH) * 180 / Math.PI / 15;
  const tz = isUkraineDST(y, m, d) ? 3 : 2;
  const noon = 12 - (lon - 15 * tz) / 15;
  return { sunrise: noon - Hhours, sunset: noon + Hhours };
}

const solarCache = new Map();
function solarForDate(dateStr) {
  let v = solarCache.get(dateStr);
  if (v !== undefined) return v;
  const [y, m, d] = dateStr.split('-').map(Number);
  v = solarTimes(y, m, d, MEAN_LAT, MEAN_LON);
  solarCache.set(dateStr, v);
  return v;
}

// Aggregate solar window over the current pool's dates.
let solarSummary = null;
function recomputeSolarSummary() {
  const dates = new Set(activePool.map(e => e.date));
  let srSum = 0, ssSum = 0, n = 0;
  let srMin = Infinity, srMax = -Infinity, ssMin = Infinity, ssMax = -Infinity;
  for (const d of dates) {
    const s = solarForDate(d);
    if (!s) continue;
    srSum += s.sunrise; ssSum += s.sunset; n++;
    if (s.sunrise < srMin) srMin = s.sunrise;
    if (s.sunrise > srMax) srMax = s.sunrise;
    if (s.sunset  < ssMin) ssMin = s.sunset;
    if (s.sunset  > ssMax) ssMax = s.sunset;
  }
  solarSummary = n ? {
    sunrise: srSum / n, sunset: ssSum / n,
    srMin, srMax, ssMin, ssMax,
  } : null;
}

// Build hour scale: tick every hour, labelled every 3h.
for (let h = 0; h <= 24; h++) {
  const pct = (h / 24) * 100;
  const tick = document.createElement('div');
  tick.className = 'scrub-tick ' + (h % 3 === 0 ? 'major' : 'minor');
  tick.style.left = pct + '%';
  axis.appendChild(tick);
  if (h % 3 === 0) {
    const lbl = document.createElement('div');
    lbl.className = 'scrub-label';
    lbl.style.left = pct + '%';
    lbl.textContent = String(h).padStart(2, '0') + ':00';
    axis.appendChild(lbl);
  }
}

function fmtTod(secs) {
  secs = ((secs % 86400) + 86400) % 86400;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
}

const HIST_BINS = 96;            // 15-minute buckets across 24 h
const HIST_BIN_SECS = 86400 / HIST_BINS;

function inAreaFilter(e) {
  // Stats are constrained only by the user-drawn shape. When nothing is
  // drawn there's no spatial filter — the entire activePool counts.
  if (!selectionPolygon) return true;
  return pointInPolygon(e.lat, e.lon, selectionPolygon);
}

function recomputeHistBins() {
  histBins = new Array(HIST_BINS).fill(0);
  for (const e of activePool) {
    if (!inAreaFilter(e)) continue;
    histBins[Math.min(HIST_BINS - 1, Math.floor(e.tod / HIST_BIN_SECS))]++;
  }
}

function eventPassesFilters(e) {
  if (!enabledTypes.has(e.type)) return false;
  // A row with no tags only passes when *all* tags are enabled (i.e. user
  // hasn't narrowed by tag) — otherwise tag-less rows would dominate.
  if (enabledTags.size === allTags.length) return true;
  if (!e.tags.length) return false;
  for (const t of e.tags) if (enabledTags.has(t)) return true;
  return false;
}

function rebuildPool() {
  const ym = monthSel.value;
  const base = ym ? EVENTS.filter(e => e.date.startsWith(ym)) : EVENTS;
  activePool = base.filter(eventPassesFilters);
  const poolN = activePool.length;
  elHudPool.textContent = poolN.toLocaleString('uk-UA');
  const ymDays = new Set(activePool.map(e => e.date)).size;
  elClock.textContent = ym
    ? `${monthLabel(ym)} · ${ymDays} ДНІВ`
    : `__DAYS__ ДНІВ · __DATE_RANGE__`;
  recomputeHistBins();
  recomputeSolarSummary();
  drawHistogram();
}

// Slider value = CENTRE of the active window. These helpers translate that
// centre into a [start, end) span that may wrap past midnight.
function windowBounds() {
  const center = parseInt(slider.value, 10);
  const win    = currentWindow();
  const half   = win / 2;
  // start lives in [0, 86400); end can exceed 86400 to indicate wrap.
  const start  = ((center - half) % 86400 + 86400) % 86400;
  const end    = start + win;
  return { center, win, start, end };
}
function inWindowTod(tod, b) {
  return b.end <= 86400
    ? (tod >= b.start && tod < b.end)
    : (tod >= b.start || tod < (b.end - 86400));
}

function drawHistogram() {
  const cssW = histCanvas.clientWidth;
  const cssH = histCanvas.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  histCanvas.width  = Math.max(1, Math.round(cssW * dpr));
  histCanvas.height = Math.max(1, Math.round(cssH * dpr));
  const ctx = histCanvas.getContext('2d');
  ctx.clearRect(0, 0, histCanvas.width, histCanvas.height);

  const max = Math.max(1, ...histBins);
  const W = histCanvas.width;
  const H = histCanvas.height;
  const padTop = 4 * dpr;
  const innerH = H - padTop;

  const b = windowBounds();

  // ── Daylight band (behind everything else) ───────────────
  // Faint gold fill from earliest sunrise to latest sunset, with a
  // slightly stronger band for "definitely-daylight" (latest sunrise →
  // earliest sunset) so the seasonal spread reads visually.
  if (solarSummary) {
    const ss = solarSummary;
    const hourToX = (h) => Math.max(0, Math.min(1, h / 24)) * W;
    const fillBand = (a, b2, alpha) => {
      const xa = hourToX(a), xb = hourToX(b2);
      ctx.fillStyle = `rgba(245, 200, 80, ${alpha})`;
      ctx.fillRect(xa, 0, xb - xa, H);
    };
    fillBand(ss.srMin, ss.ssMax, 0.05);  // any-daylight band
    fillBand(ss.srMax, ss.ssMin, 0.05);  // guaranteed-daylight overlay
  }

  // Day-grid: light lines every 3 h.
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  for (let h = 0; h <= 24; h += 3) {
    const x = Math.round((h / 24) * W) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, 2); ctx.lineTo(x, H - 1); ctx.stroke();
  }

  // Bars: dim grey outside the window, orange inside.
  let peakBin = -1, peakCount = 0;
  for (let i = 0; i < HIST_BINS; i++) {
    if (histBins[i] > peakCount) { peakCount = histBins[i]; peakBin = i; }
    const v = histBins[i] / max;
    if (v <= 0) continue;
    const x0 = Math.floor((i     / HIST_BINS) * W);
    const x1 = Math.floor(((i+1) / HIST_BINS) * W);
    const w  = Math.max(1, x1 - x0 - 1);
    const barH = Math.max(1, Math.round(v * innerH));
    const y    = padTop + innerH - barH;
    const binMidTod = (i + 0.5) * HIST_BIN_SECS;
    ctx.fillStyle = inWindowTod(binMidTod, b) ? '#ff8b3d' : 'rgba(150,160,175,0.40)';
    ctx.fillRect(x0, y, w, barH);
  }

  // Peak marker (blue triangle + dashed line).
  if (peakCount > 0) {
    const peakStart = peakBin * HIST_BIN_SECS;
    const peakCenter = peakStart + HIST_BIN_SECS / 2;
    const pcx = (peakCenter / 86400) * W;
    ctx.fillStyle = 'rgba(109,182,255,0.95)';
    ctx.beginPath();
    ctx.moveTo(pcx, padTop);
    ctx.moveTo(pcx, padTop + 2);
    ctx.lineTo(pcx - 5 * dpr, padTop - 5 * dpr);
    ctx.lineTo(pcx + 5 * dpr, padTop - 5 * dpr);
    ctx.closePath(); ctx.fill();
    ctx.strokeStyle = 'rgba(109,182,255,0.40)';
    ctx.setLineDash([3 * dpr, 4 * dpr]);
    ctx.beginPath(); ctx.moveTo(pcx, padTop); ctx.lineTo(pcx, H); ctx.stroke();
    ctx.setLineDash([]);

    elHudPeak.textContent = peakCount.toLocaleString('uk-UA');
    elHudPeakTime.textContent = `${fmtTod(peakStart)}–${fmtTod(peakStart + HIST_BIN_SECS)}`;
  } else {
    elHudPeak.textContent = '0';
    elHudPeakTime.textContent = '—';
  }

  // ── Sunrise / sunset marker lines + labels ───────────────
  if (solarSummary) {
    const ss = solarSummary;
    const xOf = (h) => (h / 24) * W;
    const drawSunLine = (h, glyph, color) => {
      const x = xOf(h);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.setLineDash([2 * dpr, 3 * dpr]);
      ctx.beginPath();
      ctx.moveTo(x + 0.5, padTop);
      ctx.lineTo(x + 0.5, H);
      ctx.stroke();
      ctx.setLineDash([]);
      // Label
      const hh = Math.floor(h), mm = Math.round((h - hh) * 60);
      const label = `${glyph} ${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}`;
      ctx.font = `${10 * dpr}px 'JetBrains Mono', monospace`;
      ctx.textBaseline = 'top';
      ctx.fillStyle = color;
      const tw = ctx.measureText(label).width;
      const tx = Math.max(2, Math.min(W - tw - 2, x + 4));
      ctx.fillRect(tx - 3, padTop, tw + 6, 14 * dpr);
      ctx.fillStyle = '#000';
      ctx.fillText(label, tx, padTop + 2);
    };
    drawSunLine(ss.sunrise, '☀↑', 'rgba(245,200,80,0.95)');
    drawSunLine(ss.sunset,  '☾',  'rgba(140,180,255,0.95)');
  }
}

function update() {
  const b = windowBounds();
  const start = b.start, end = b.end, win = b.win;
  const visible = activePool.filter(e => inWindowTod(e.tod, b));

  // One marker per event — no aggregation, no clustering.
  markerLayer.clearLayers();
  const esc = (s) => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  for (const e of visible) {
    const col = typeColor(e.type);
    const marker = L.circleMarker([e.lat, e.lon], {
      renderer: markerRenderer,
      radius: 5,
      color: col,
      weight: 1,
      fillColor: col,
      fillOpacity: 0.55,
    });
    const meta = [e.name, e.type, e.comment].filter(s => s).join(' · ');
    marker.bindPopup(
      `<b>${e.date} ${e.time}</b><br>` +
      (e.place ? esc(e.place) + '<br>' : '') +
      `${e.lat.toFixed(5)}, ${e.lon.toFixed(5)}` +
      (meta ? '<hr style="margin:4px 0">' + esc(meta) : '')
    );
    markerLayer.addLayer(marker);
  }

  // Stats reflect the area filter (selection if drawn, else viewport).
  let inAreaCount = 0;
  for (const e of visible) { if (inAreaFilter(e)) inAreaCount++; }
  const poolN = activePool.length || 1;
  elHudBig.textContent   = inAreaCount.toLocaleString('uk-UA');
  elHudPct.textContent   = ((inAreaCount / poolN) * 100).toFixed(1) + '%';
  elWinRange.textContent = `${fmtTod(start)} – ${fmtTod(end)}`;

  // Always redraw the histogram so bar colours track the window.
  drawHistogram();

  // Draw window band(s) on the scrubber track, handling midnight wrap.
  const startPct = (start / 86400) * 100;
  const endPct = ((start + win) / 86400) * 100;
  if (endPct <= 100) {
    band1.style.left = startPct + '%';
    band1.style.width = (endPct - startPct) + '%';
    band2.style.display = 'none';
  } else {
    band1.style.left = startPct + '%';
    band1.style.width = (100 - startPct) + '%';
    band2.style.display = 'block';
    band2.style.left = '0%';
    band2.style.width = (endPct - 100) + '%';
  }
}

slider.addEventListener('input', update);
monthSel.addEventListener('change', () => { rebuildPool(); update(); });
window.addEventListener('resize', () => { drawHistogram(); update(); });

let playing = false;
let timer = null;
function setPlaying(on) {
  playing = on;
  playLabel.textContent = on ? 'ПАУЗА' : 'ВІДТВОРИТИ';
  playBtn.querySelector('.icon').innerHTML = on ? '&#10074;&#10074;' : '&#9654;';
  clearInterval(timer);
  if (on) {
    // Advance 15 min every 200 ms → full 24 h sweep in ~19 s.
    timer = setInterval(() => {
      let v = parseInt(slider.value, 10) + 900;
      if (v > 86340) v = 0;
      slider.value = v;
      update();
    }, 200);
  }
}
playBtn.addEventListener('click', () => setPlaying(!playing));
resetBtn.addEventListener('click', () => { setPlaying(false); slider.value = 43200; update(); });

// Keyboard shortcuts.
window.addEventListener('keydown', (e) => {
  if (e.target && /input|select|textarea/i.test(e.target.tagName)) return;
  if (e.code === 'Space') { e.preventDefault(); setPlaying(!playing); }
  else if (e.code === 'ArrowRight') {
    setPlaying(false);
    slider.value = Math.min(86340, parseInt(slider.value, 10) + currentWindow());
    update();
  } else if (e.code === 'ArrowLeft') {
    setPlaying(false);
    slider.value = Math.max(0, parseInt(slider.value, 10) - currentWindow());
    update();
  }
});

rebuildPool();
update();
</script>
</body>
</html>
"""


def main():
    events = parse_rows()
    dates = sorted({e["date"] for e in events})
    date_range = f"{dates[0]} → {dates[-1]}"
    html = (
        HTML_TEMPLATE
        .replace("__DATA__", json.dumps(events, separators=(",", ":")))
        .replace("__TOTAL__", str(len(events)))
        .replace("__DAYS__", str(len(dates)))
        .replace("__DATE_RANGE__", date_range)
    )
    OUT_PATH.write_text(html)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
