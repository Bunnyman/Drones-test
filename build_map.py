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


CSV_PATH = Path("/root/.claude/uploads/5554a83c-6e5b-498c-9c56-2ea45dff2711/814c6f5c-trackendpoints0105202601062026.csv")
OUT_PATH = Path(__file__).parent / "drones_map.html"

COL_TIME    = "Час останньої фіксації"
COL_COORDS  = "Координати останньої точки"
COL_PLACE   = "Найближчий населений пункт"
COL_NAME    = "Назва цілі"
COL_TYPE    = "Тип цілі"
COL_TAGS    = "Теги"
COL_COMMENT = "Коментар"


def parse_rows():
    events = []
    skipped = 0
    with CSV_PATH.open(encoding="utf-8-sig") as f:
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
    print(f"Parsed {len(events)} events (skipped {skipped})", file=sys.stderr)
    return events


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Drone events &mdash; time scrubber</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
<style>
  html, body { margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  #map { position: absolute; top: 0; bottom: 240px; left: 0; right: 0; }
  #panel {
    position: absolute; bottom: 0; left: 0; right: 0; height: 240px;
    background: #1e1e1e; color: #eee; padding: 10px 16px; box-sizing: border-box;
    display: flex; flex-direction: column; gap: 6px; z-index: 1000;
    box-shadow: 0 -2px 8px rgba(0,0,0,.4);
  }
  #row1, #row2 { display: flex; align-items: center; gap: 12px; font-size: 13px; flex-wrap: wrap; }
  .filter-group {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 2px 8px 2px 6px;
    background: #2a2a2a;
    border-radius: 4px;
  }
  .filter-group > .lbl {
    font-size: 11px; opacity: .7; text-transform: uppercase; letter-spacing: .04em;
  }
  .pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 8px;
    border: 1px solid transparent;
    border-radius: 999px;
    font-size: 12px;
    cursor: pointer;
    user-select: none;
    background: transparent;
    color: #aaa;
  }
  .pill .swatch {
    display: inline-block;
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--col, #888);
    box-shadow: 0 0 0 1px rgba(255,255,255,0.15);
  }
  .pill.active {
    background: var(--col, #555);
    color: #fff;
    border-color: var(--col, #555);
  }
  .pill.active .swatch { background: #fff; box-shadow: 0 0 0 1px rgba(0,0,0,0.25); }
  .pill:not(.active):hover { color: #fff; border-color: rgba(255,255,255,0.2); }
  button {
    background: #2d7; border: 0; color: #111; padding: 6px 12px;
    border-radius: 4px; cursor: pointer; font-weight: 600;
  }
  button:hover { background: #5fb; }
  #current { font-weight: 600; min-width: 220px; }
  #count { color: #5fb; font-weight: 600; }
  #peak { color: #aaa; font-size: 12px; margin-left: auto; }
  #areaStatus {
    display: none;
    background: rgba(95, 255, 180, 0.18);
    border: 1px solid #5fb;
    color: #cfe;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 12px;
  }
  #areaStatus a {
    color: #fff;
    margin-left: 6px;
    cursor: pointer;
    text-decoration: underline;
  }
  #areaStatus.active { display: inline-block; }
  select { background: #333; color: #eee; border: 1px solid #555; padding: 4px; border-radius: 3px; }
  label { font-size: 12px; opacity: .8; }

  /* --- scrubber --- */
  /* Layout (y, top-aligned):
       0..60   histogram canvas
      60..72   slider track (12 px)
      55..77   slider thumb (22 px, vertically centred on track)
      78..100  axis ticks + hour labels
     The window band is overlaid on top, spanning histogram + track. */
  #scrub {
    position: relative;
    height: 105px;
    margin-top: 4px;
  }
  #hist {
    position: absolute;
    top: 0; left: 7px;
    width: calc(100% - 14px);
    height: 60px;
    background: #181818;
    border-radius: 4px 4px 0 0;
    display: block;
  }
  #scrub-track {
    position: absolute;
    top: 60px; left: 7px;
    width: calc(100% - 14px);
    height: 12px;
    background: #333;
    border-radius: 0 0 4px 4px;
    overflow: hidden;
  }
  .scrub-band {
    position: absolute;
    top: 0;
    height: 72px;            /* hist (60) + track (12) */
    background: rgba(255, 255, 255, 0.10);
    border-left: 2px solid #fff;
    border-right: 2px solid #fff;
    box-sizing: border-box;
    pointer-events: none;
  }
  #slider {
    position: absolute;
    top: 55px; left: 0; right: 0;
    width: 100%;
    margin: 0;
    -webkit-appearance: none;
    appearance: none;
    background: transparent;
    height: 22px;
  }
  #slider::-webkit-slider-runnable-track {
    background: transparent;
    height: 22px;
    border: 0;
  }
  #slider::-moz-range-track {
    background: transparent;
    height: 22px;
    border: 0;
  }
  #slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 22px;
    background: #fff;
    border: 1px solid #000;
    border-radius: 3px;
    cursor: pointer;
    box-shadow: 0 0 4px rgba(0,0,0,.6);
  }
  #slider::-moz-range-thumb {
    width: 14px;
    height: 22px;
    background: #fff;
    border: 1px solid #000;
    border-radius: 3px;
    cursor: pointer;
    box-shadow: 0 0 4px rgba(0,0,0,.6);
  }
  #scrub-axis {
    position: absolute;
    top: 78px; left: 7px; right: 7px;
    height: 24px;
    pointer-events: none;
  }
  .scrub-tick {
    position: absolute;
    width: 1px;
    background: #777;
    top: 0;
    transform: translateX(-0.5px);
  }
  .scrub-tick.major { height: 8px; background: #aaa; }
  .scrub-tick.minor { height: 4px; }
  .scrub-label {
    position: absolute;
    top: 10px;
    font-size: 11px;
    color: #bbb;
    transform: translateX(-50%);
    white-space: nowrap;
  }
</style>
</head>
<body>
<div id="map"></div>
<div id="panel">
  <div id="row1">
    <span id="current">&mdash;</span>
    <span>In window: <span id="count">0</span> /
      <span id="poolCount">__TOTAL__</span>
      <span id="poolNote">(all __DAYS__ days, __DATE_RANGE__)</span></span>
    <span id="areaStatus">&#9633; Area selected
      <a id="clearArea">clear</a></span>
    <span id="peak">Peak: &mdash;</span>
    <label>Month:
      <select id="monthSel"></select>
    </label>
    <label>Window:
      <select id="window">
        <option value="1800">30 min</option>
        <option value="3600" selected>1 hour</option>
        <option value="7200">2 hours</option>
      </select>
    </label>
    <button id="play">&#9658; Play</button>
  </div>
  <div id="row2">
    <span class="filter-group">
      <span class="lbl">Тип цілі</span>
      <span id="typeFilters"></span>
    </span>
    <span class="filter-group">
      <span class="lbl">Теги</span>
      <span id="tagFilters"></span>
    </span>
  </div>
  <div id="scrub">
    <canvas id="hist"></canvas>
    <div id="scrub-track"></div>
    <div class="scrub-band" id="band1"></div>
    <div class="scrub-band" id="band2" style="display:none"></div>
    <input id="slider" type="range" min="0" max="86340" value="0" step="60">
    <div id="scrub-axis"></div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
<script>
const EVENTS = __DATA__;

const map = L.map('map', { preferCanvas: true });
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18,
  attribution: '&copy; OpenStreetMap'
}).addTo(map);

// Fit to all event bounds initially.
const allBounds = L.latLngBounds(EVENTS.map(e => [e.lat, e.lon]));
map.fitBounds(allBounds, { padding: [20, 20] });

const cluster = L.markerClusterGroup({
  maxClusterRadius: 45,
  spiderfyOnMaxZoom: true,
  showCoverageOnHover: false,
});
map.addLayer(cluster);

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
    rectangle: { shapeOptions: { color: '#5fb', weight: 2, fillOpacity: 0.05 } },
    polygon: { shapeOptions: { color: '#5fb', weight: 2, fillOpacity: 0.05 },
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
  'FPV':   '#e74c3c',
  'Крило': '#3498db',
  'БПЛА':  '#2ecc71',
  '':      '#888',
};
const TYPE_FALLBACK_PALETTE = ['#f39c12','#9b59b6','#1abc9c','#e67e22','#16a085'];
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

function buildPillRow(host, items, enabledSet, labelFn, colorFn, onChange) {
  host.innerHTML = '';
  for (const it of items) {
    const pill = document.createElement('span');
    pill.className = 'pill active';
    if (colorFn) pill.style.setProperty('--col', colorFn(it));
    if (colorFn) {
      const sw = document.createElement('span');
      sw.className = 'swatch';
      sw.style.background = colorFn(it);
      pill.appendChild(sw);
    }
    const txt = document.createElement('span');
    txt.textContent = labelFn(it);
    pill.appendChild(txt);
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
  (t) => t === '' ? '(не визначено)' : t,
  (t) => typeColor(t),
  () => { rebuildPool(); update(); }
);
buildPillRow(
  document.getElementById('tagFilters'),
  allTags, enabledTags,
  (t) => t.replace(/^credibility:\s*/, 'cred · '),
  null,
  () => { rebuildPool(); update(); }
);

const slider = document.getElementById('slider');
const currentLabel = document.getElementById('current');
const countLabel = document.getElementById('count');
const poolCount = document.getElementById('poolCount');
const poolNote = document.getElementById('poolNote');
const windowSel = document.getElementById('window');
const monthSel = document.getElementById('monthSel');
const playBtn = document.getElementById('play');
const band1 = document.getElementById('band1');
const band2 = document.getElementById('band2');
const axis = document.getElementById('scrub-axis');
const histCanvas = document.getElementById('hist');
const peakLabel = document.getElementById('peak');

// --- Month selector: "All time" plus every YYYY-MM present in data. ---
const monthSet = new Set(EVENTS.map(e => e.date.slice(0, 7)));
const months = [...monthSet].sort();
const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function monthLabel(ym) {
  const [y, m] = ym.split('-');
  return `${MONTH_NAMES[parseInt(m,10)-1]} ${y}`;
}
const optAll = document.createElement('option');
optAll.value = ''; optAll.textContent = 'All time';
monthSel.appendChild(optAll);
for (const ym of months) {
  const o = document.createElement('option');
  o.value = ym; o.textContent = monthLabel(ym);
  monthSel.appendChild(o);
}

let activePool = EVENTS;   // events left after month filter
let histBins = [];         // histogram of (activePool ∩ viewport) over 24 h

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
  // When a selection polygon exists, the stats use it. Otherwise we
  // fall back to the current map viewport so things still make sense.
  if (selectionPolygon) return pointInPolygon(e.lat, e.lon, selectionPolygon);
  return map.getBounds().contains([e.lat, e.lon]);
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
  poolCount.textContent = activePool.length;
  const monthNote = ym
    ? `${monthLabel(ym)}, ${new Set(activePool.map(e => e.date)).size} day${activePool.length===1?'':'s'}`
    : `all __DAYS__ days, __DATE_RANGE__`;
  const filterNote =
    (enabledTypes.size === allTypes.length ? '' : ` · ${enabledTypes.size}/${allTypes.length} types`) +
    (enabledTags.size  === allTags.length  ? '' : ` · ${enabledTags.size}/${allTags.length} tags`);
  poolNote.textContent = `(${monthNote}${filterNote})`;
  recomputeHistBins();
  drawHistogram();
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

  // Faint horizontal grid lines at 25/50/75/100 % of max.
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 1;
  for (let g = 1; g <= 4; g++) {
    const y = Math.round(padTop + innerH - (g / 4) * innerH) + 0.5;
    ctx.beginPath();
    ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  }

  // Bars.
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
    // Solid cyan bars; brighter when taller.
    const alpha = 0.55 + 0.45 * v;
    ctx.fillStyle = `rgba(95, 200, 255, ${alpha})`;
    ctx.fillRect(x0, y, w, barH);
  }

  if (peakCount > 0) {
    const peakStart = peakBin * HIST_BIN_SECS;
    peakLabel.textContent =
      `Peak: ${fmtTod(peakStart)}–${fmtTod(peakStart + HIST_BIN_SECS)} ` +
      `(${peakCount} event${peakCount===1?'':'s'})`;
  } else {
    peakLabel.textContent = 'Peak: — (no events in view)';
  }
}

function update() {
  const start = parseInt(slider.value, 10);
  const win = parseInt(windowSel.value, 10);
  const end = start + win;

  // [start, end) with wrap-around past midnight.
  const inWindow = (tod) => {
    if (end <= 86400) return tod >= start && tod < end;
    return tod >= start || tod < (end - 86400);
  };
  const visible = activePool.filter(e => inWindow(e.tod));

  // Aggregate by rounded location across ALL dates.
  const key = (e) => `${e.lat.toFixed(4)},${e.lon.toFixed(4)}`;
  const groups = new Map();
  for (const e of visible) {
    const k = key(e);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(e);
  }

  cluster.clearLayers();
  for (const list of groups.values()) {
    const first = list[0];
    const n = list.length;
    const radius = 6 + Math.min(22, Math.sqrt(n) * 3.5);
    // Colour by the most common type in this co-located group.
    const typeCounts = {};
    for (const e of list) typeCounts[e.type] = (typeCounts[e.type] || 0) + 1;
    const dominantType = Object.entries(typeCounts)
      .sort((a, b) => b[1] - a[1])[0][0];
    const col = typeColor(dominantType);
    const marker = L.circleMarker([first.lat, first.lon], {
      radius,
      color: col,
      weight: 1,
      fillColor: col,
      fillOpacity: 0.55,
    });
    const sorted = list.slice().sort((a, b) =>
      a.date === b.date ? a.time.localeCompare(b.time) : a.date.localeCompare(b.date));
    const esc = (s) => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    const lines = sorted.map(e => {
      const meta = [e.name, e.type, e.comment].filter(s => s).join(' · ');
      return `<div><b>${e.date} ${e.time}</b>${meta ? ' &mdash; ' + esc(meta) : ''}</div>`;
    });
    marker.bindPopup(
      `<b>${n} event${n>1?'s':''} at this spot</b><br>` +
      (first.place ? esc(first.place) + '<br>' : '') +
      `${first.lat.toFixed(5)}, ${first.lon.toFixed(5)}<hr style="margin:4px 0">` +
      `<div style="max-height:200px;overflow:auto;font-size:12px">${lines.join('')}</div>`
    );
    cluster.addLayer(marker);
  }

  // Stats reflect the area filter (selection if drawn, else viewport).
  let inAreaCount = 0;
  for (const e of visible) { if (inAreaFilter(e)) inAreaCount++; }
  countLabel.textContent = inAreaCount;
  currentLabel.textContent =
    `Window ${fmtTod(start)} – ${fmtTod(start + win)}  (any date)`;

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
windowSel.addEventListener('change', update);
monthSel.addEventListener('change', () => { rebuildPool(); update(); });
window.addEventListener('resize', drawHistogram);
map.on('moveend zoomend', () => { recomputeHistBins(); drawHistogram(); });

let playing = false;
let timer = null;
playBtn.addEventListener('click', () => {
  playing = !playing;
  playBtn.innerHTML = playing ? '&#10074;&#10074; Pause' : '&#9658; Play';
  if (playing) {
    // Advance 15 min every 200 ms → full 24 h sweep in ~19 s.
    timer = setInterval(() => {
      let v = parseInt(slider.value, 10) + 900;
      if (v > 86340) v = 0;
      slider.value = v;
      update();
    }, 200);
  } else {
    clearInterval(timer);
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
