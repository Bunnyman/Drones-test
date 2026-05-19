#!/usr/bin/env python3
"""Convert the drone events CSV into an interactive HTML map with a 1-hour time scrubber."""

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import mgrs

CSV_PATH = Path("/root/.claude/uploads/a6225105-8a3e-41a6-b9c3-249c809118bc/2bd6693e-events.csv")
OUT_PATH = Path(__file__).parent / "drones_map.html"

MGRS_RE = re.compile(r"(\d{1,2}[A-Z])\s*([A-Z]{2})\s*(\d{5})\s*(\d{5})")


def parse_rows():
    converter = mgrs.MGRS()
    events = []
    skipped = 0
    with CSV_PATH.open() as f:
        for row in csv.DictReader(f):
            lat_raw = (row.get("lat") or "").strip()
            lon_raw = (row.get("lon") or "").strip()
            mgrs_str = ""
            m = MGRS_RE.search(row.get("mgrs") or "")
            if m:
                mgrs_str = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}"

            if lat_raw and lon_raw:
                try:
                    lat = float(lat_raw)
                    lon = float(lon_raw)
                except ValueError:
                    skipped += 1
                    continue
            elif mgrs_str:
                try:
                    lat, lon = converter.toLatLon(mgrs_str)
                except Exception:
                    skipped += 1
                    continue
            else:
                skipped += 1
                continue
            try:
                ts = datetime.fromisoformat(f"{row['date']}T{row['time']}")
            except ValueError:
                skipped += 1
                continue
            tod = ts.hour * 3600 + ts.minute * 60 + ts.second
            events.append({
                "tod": tod,
                "date": row["date"],
                "time": row["time"],
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "mgrs": mgrs_str,
                "comment": (row.get("comment") or "").strip(),
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
<style>
  html, body { margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  #map { position: absolute; top: 0; bottom: 140px; left: 0; right: 0; }
  #panel {
    position: absolute; bottom: 0; left: 0; right: 0; height: 140px;
    background: #1e1e1e; color: #eee; padding: 10px 16px; box-sizing: border-box;
    display: flex; flex-direction: column; gap: 4px; z-index: 1000;
    box-shadow: 0 -2px 8px rgba(0,0,0,.4);
  }
  #row1 { display: flex; align-items: center; gap: 12px; font-size: 13px; }
  button {
    background: #2d7; border: 0; color: #111; padding: 6px 12px;
    border-radius: 4px; cursor: pointer; font-weight: 600;
  }
  button:hover { background: #5fb; }
  #current { font-weight: 600; min-width: 220px; }
  #count { color: #5fb; font-weight: 600; }
  select { background: #333; color: #eee; border: 1px solid #555; padding: 4px; border-radius: 3px; }
  label { font-size: 12px; opacity: .8; }

  /* --- scrubber --- */
  #scrub {
    position: relative;
    height: 70px;
    margin-top: 4px;
  }
  /* Track is inset by half the thumb width (7px) so its 0–100 % range
     matches the actual travel of the slider thumb. */
  #scrub-track {
    position: absolute;
    top: 22px; left: 7px; right: 7px;
    height: 14px;
    background: #222;
    border-radius: 7px;
    overflow: hidden;
  }
  #heat {
    position: absolute;
    inset: 0;
    width: 100%; height: 100%;
    image-rendering: pixelated;
  }
  .scrub-band {
    position: absolute;
    top: 0; bottom: 0;
    background: rgba(255, 255, 255, 0.18);
    border-left: 2px solid #fff;
    border-right: 2px solid #fff;
    box-sizing: border-box;
    box-shadow: 0 0 0 1px rgba(0,0,0,.4) inset;
  }
  #slider {
    position: absolute;
    top: 16px; left: 0; right: 0;
    width: 100%;
    margin: 0;
    -webkit-appearance: none;
    appearance: none;
    background: transparent;
    height: 24px;
  }
  #slider::-webkit-slider-runnable-track {
    background: transparent;
    height: 24px;
    border: 0;
  }
  #slider::-moz-range-track {
    background: transparent;
    height: 24px;
    border: 0;
  }
  #slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 26px;
    background: #fff;
    border: 1px solid #000;
    border-radius: 3px;
    cursor: pointer;
    margin-top: -1px;
    box-shadow: 0 0 4px rgba(0,0,0,.6);
  }
  #slider::-moz-range-thumb {
    width: 14px;
    height: 26px;
    background: #fff;
    border: 1px solid #000;
    border-radius: 3px;
    cursor: pointer;
    box-shadow: 0 0 4px rgba(0,0,0,.6);
  }
  #scrub-axis {
    position: absolute;
    top: 44px; left: 7px; right: 7px;
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
    <span style="flex:1"></span>
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
  <div id="scrub">
    <div id="scrub-track">
      <canvas id="heat"></canvas>
      <div class="scrub-band" id="band1"></div>
      <div class="scrub-band" id="band2" style="display:none"></div>
    </div>
    <input id="slider" type="range" min="0" max="86340" value="0" step="60">
    <div id="scrub-axis"></div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
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
const heatCanvas = document.getElementById('heat');

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
let heatBins = [];         // histogram of activePool over 24 h

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

// Map a 0..1 value to a "heat" colour (dark → blue → cyan → yellow → red).
function heatColor(v) {
  if (v <= 0) return 'rgba(0,0,0,0)';
  // Five-stop gradient.
  const stops = [
    [0.00, [ 40,  40,  80]],
    [0.15, [ 30,  90, 180]],
    [0.40, [ 70, 200, 200]],
    [0.70, [255, 220,  60]],
    [1.00, [220,  40,  40]],
  ];
  v = Math.max(0, Math.min(1, v));
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i][0]) {
      const [a, b] = [stops[i-1], stops[i]];
      const t = (v - a[0]) / (b[0] - a[0]);
      const r = Math.round(a[1][0] + t * (b[1][0] - a[1][0]));
      const g = Math.round(a[1][1] + t * (b[1][1] - a[1][1]));
      const bl= Math.round(a[1][2] + t * (b[1][2] - a[1][2]));
      return `rgb(${r},${g},${bl})`;
    }
  }
  return 'rgb(220,40,40)';
}

const HEAT_BINS = 288;          // 5-minute buckets across 24 h
const HEAT_BIN_SECS = 86400 / HEAT_BINS;

function recomputeHeatBins() {
  // Heatmap reflects only events inside the current map viewport (and the
  // active month filter). Re-runs on pan/zoom and on month change.
  const bounds = map.getBounds();
  heatBins = new Array(HEAT_BINS).fill(0);
  let visibleInPool = 0;
  for (const e of activePool) {
    if (!bounds.contains([e.lat, e.lon])) continue;
    heatBins[Math.min(HEAT_BINS - 1, Math.floor(e.tod / HEAT_BIN_SECS))]++;
    visibleInPool++;
  }
  return visibleInPool;
}

function rebuildPool() {
  const ym = monthSel.value;
  activePool = ym ? EVENTS.filter(e => e.date.startsWith(ym)) : EVENTS;
  poolCount.textContent = activePool.length;
  if (ym) {
    const days = new Set(activePool.map(e => e.date)).size;
    poolNote.textContent = `(${monthLabel(ym)}, ${days} day${days===1?'':'s'})`;
  } else {
    poolNote.textContent = `(all __DAYS__ days, __DATE_RANGE__)`;
  }
  recomputeHeatBins();
  drawHeatmap();
}

function drawHeatmap() {
  // Match the CSS pixel size of the track so 1 bin = 1 px column scaled.
  const cssW = heatCanvas.clientWidth || heatCanvas.parentElement.clientWidth;
  const cssH = heatCanvas.clientHeight || heatCanvas.parentElement.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  heatCanvas.width  = Math.max(1, Math.round(cssW * dpr));
  heatCanvas.height = Math.max(1, Math.round(cssH * dpr));
  const ctx = heatCanvas.getContext('2d');
  ctx.clearRect(0, 0, heatCanvas.width, heatCanvas.height);

  const max = Math.max(1, ...heatBins);
  // Use sqrt scaling so quiet hours stay visible without saturating peaks.
  const norm = (n) => Math.sqrt(n / max);
  const W = heatCanvas.width;
  const H = heatCanvas.height;
  for (let i = 0; i < HEAT_BINS; i++) {
    const x0 = Math.floor((i     / HEAT_BINS) * W);
    const x1 = Math.floor(((i+1) / HEAT_BINS) * W);
    ctx.fillStyle = heatColor(norm(heatBins[i]));
    ctx.fillRect(x0, 0, x1 - x0, H);
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
    const marker = L.circleMarker([first.lat, first.lon], {
      radius,
      color: '#ff3030',
      weight: 1,
      fillColor: '#ff5050',
      fillOpacity: 0.55,
    });
    const sorted = list.slice().sort((a, b) =>
      a.date === b.date ? a.time.localeCompare(b.time) : a.date.localeCompare(b.date));
    const lines = sorted.map(e =>
      `<div>${e.date} ${e.time}${e.comment ? ' &mdash; ' + e.comment.replace(/</g,'&lt;') : ''}</div>`
    );
    marker.bindPopup(
      `<b>${n} event${n>1?'s':''} at this spot</b><br>` +
      `MGRS: ${first.mgrs}<br>` +
      `${first.lat.toFixed(5)}, ${first.lon.toFixed(5)}<hr style="margin:4px 0">` +
      `<div style="max-height:200px;overflow:auto;font-size:12px">${lines.join('')}</div>`
    );
    cluster.addLayer(marker);
  }

  countLabel.textContent = visible.length;
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
window.addEventListener('resize', drawHeatmap);
map.on('moveend zoomend', () => { recomputeHeatBins(); drawHeatmap(); });

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
