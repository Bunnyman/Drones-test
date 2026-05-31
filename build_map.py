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
            events.append({
                "tod": tod,
                "date": ts.strftime("%Y-%m-%d"),
                "time": ts.strftime("%H:%M:%S"),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "name": (row.get(COL_NAME) or "").strip(),
                "type": (row.get(COL_TYPE) or "").strip(),
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
<style>
  html, body { margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  #map { position: absolute; top: 0; bottom: 200px; left: 0; right: 0; }
  #panel {
    position: absolute; bottom: 0; left: 0; right: 0; height: 200px;
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
  #peak { color: #aaa; font-size: 12px; margin-left: auto; }
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

function recomputeHistBins() {
  // Histogram reflects only events inside the current map viewport (and the
  // active month filter). Re-runs on pan/zoom and on month change.
  const bounds = map.getBounds();
  histBins = new Array(HIST_BINS).fill(0);
  for (const e of activePool) {
    if (!bounds.contains([e.lat, e.lon])) continue;
    histBins[Math.min(HIST_BINS - 1, Math.floor(e.tod / HIST_BIN_SECS))]++;
  }
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
    const marker = L.circleMarker([first.lat, first.lon], {
      radius,
      color: '#ff3030',
      weight: 1,
      fillColor: '#ff5050',
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
