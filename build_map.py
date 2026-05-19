#!/usr/bin/env python3
"""Convert the drone events CSV into an interactive HTML map with a 1-hour time scrubber."""

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import mgrs

CSV_PATH = Path("/root/.claude/uploads/fe57542c-52bb-495e-8210-f0705ca7e96d/9c2802f6-events.csv")
OUT_PATH = Path(__file__).parent / "drones_map.html"

MGRS_RE = re.compile(r"(\d{1,2}[A-Z])\s*([A-Z]{2})\s*(\d{5})\s*(\d{5})")


def parse_rows():
    converter = mgrs.MGRS()
    events = []
    skipped = 0
    with CSV_PATH.open() as f:
        for row in csv.DictReader(f):
            raw = row.get("mgrs") or ""
            m = MGRS_RE.search(raw)
            if not m:
                skipped += 1
                continue
            mgrs_str = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}"
            try:
                lat, lon = converter.toLatLon(mgrs_str)
            except Exception:
                skipped += 1
                continue
            try:
                ts = datetime.fromisoformat(f"{row['date']}T{row['time']}")
            except ValueError:
                skipped += 1
                continue
            events.append({
                "t": int(ts.timestamp()),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "mgrs": mgrs_str,
                "comment": (row.get("comment") or "").strip(),
            })
    events.sort(key=lambda e: e["t"])
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
  #map { position: absolute; top: 0; bottom: 110px; left: 0; right: 0; }
  #panel {
    position: absolute; bottom: 0; left: 0; right: 0; height: 110px;
    background: #1e1e1e; color: #eee; padding: 10px 16px; box-sizing: border-box;
    display: flex; flex-direction: column; gap: 6px; z-index: 1000;
    box-shadow: 0 -2px 8px rgba(0,0,0,.4);
  }
  #row1 { display: flex; align-items: center; gap: 12px; font-size: 13px; }
  #row2 { display: flex; align-items: center; gap: 12px; }
  #slider { flex: 1; }
  button {
    background: #2d7; border: 0; color: #111; padding: 6px 12px;
    border-radius: 4px; cursor: pointer; font-weight: 600;
  }
  button:hover { background: #5fb; }
  #current { font-weight: 600; min-width: 180px; }
  #count { color: #5fb; font-weight: 600; }
  .legend {
    background: rgba(30,30,30,.85); color: #eee; padding: 6px 10px;
    border-radius: 4px; font-size: 12px; line-height: 1.4;
  }
  select { background: #333; color: #eee; border: 1px solid #555; padding: 4px; border-radius: 3px; }
  label { font-size: 12px; opacity: .8; }
</style>
</head>
<body>
<div id="map"></div>
<div id="panel">
  <div id="row1">
    <span id="current">&mdash;</span>
    <span>Events in window: <span id="count">0</span> / __TOTAL__</span>
    <span style="flex:1"></span>
    <label>Window:
      <select id="window">
        <option value="1800">30 min (&plusmn;15m)</option>
        <option value="3600" selected>1 hour (&plusmn;30m)</option>
        <option value="7200">2 hours (&plusmn;1h)</option>
        <option value="21600">6 hours (&plusmn;3h)</option>
      </select>
    </label>
    <label>Speed:
      <select id="speed">
        <option value="900">15 min / s</option>
        <option value="1800" selected>30 min / s</option>
        <option value="3600">1 h / s</option>
        <option value="10800">3 h / s</option>
      </select>
    </label>
    <button id="play">&#9658; Play</button>
  </div>
  <div id="row2">
    <input id="slider" type="range" min="0" max="100" value="0" step="1">
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const EVENTS = __DATA__;

const tMin = EVENTS[0].t;
const tMax = EVENTS[EVENTS.length - 1].t;

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
const windowSel = document.getElementById('window');
const speedSel = document.getElementById('speed');
const playBtn = document.getElementById('play');

// Range covers tMin..tMax in 60-second steps.
slider.min = tMin;
slider.max = tMax;
slider.step = 60;
slider.value = tMin;

function fmt(ts) {
  const d = new Date(ts * 1000);
  return d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
}

function update() {
  const center = parseInt(slider.value, 10);
  const half = parseInt(windowSel.value, 10) / 2;
  const lo = center - half;
  const hi = center + half;
  const visible = EVENTS.filter(e => e.t >= lo && e.t <= hi);

  // Aggregate by rounded location so co-located events share a marker.
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
    const radius = 6 + Math.min(20, Math.sqrt(n) * 3);
    const marker = L.circleMarker([first.lat, first.lon], {
      radius,
      color: '#ff3030',
      weight: 1,
      fillColor: '#ff5050',
      fillOpacity: 0.55,
    });
    const lines = list.map(e =>
      `<div>${fmt(e.t)}${e.comment ? ' &mdash; ' + e.comment.replace(/</g,'&lt;') : ''}</div>`
    );
    marker.bindPopup(
      `<b>${n} event${n>1?'s':''}</b><br>` +
      `MGRS: ${first.mgrs}<br>` +
      `${first.lat.toFixed(5)}, ${first.lon.toFixed(5)}<hr style="margin:4px 0">` +
      lines.join('')
    );
    cluster.addLayer(marker);
  }

  countLabel.textContent = visible.length;
  const winLbl = (half * 2 / 3600).toFixed(half * 2 % 3600 === 0 ? 0 : 1);
  currentLabel.textContent = `${fmt(center)}  (window: ${winLbl}h)`;
}

slider.addEventListener('input', update);
windowSel.addEventListener('change', update);

let playing = false;
let timer = null;
playBtn.addEventListener('click', () => {
  playing = !playing;
  playBtn.innerHTML = playing ? '&#10074;&#10074; Pause' : '&#9658; Play';
  if (playing) {
    timer = setInterval(() => {
      const step = parseInt(speedSel.value, 10) / 10; // 10 fps
      let v = parseInt(slider.value, 10) + step;
      if (v > tMax) { v = tMin; }
      slider.value = v;
      update();
    }, 100);
  } else {
    clearInterval(timer);
  }
});

update();
</script>
</body>
</html>
"""


def main():
    events = parse_rows()
    html = (
        HTML_TEMPLATE
        .replace("__DATA__", json.dumps(events, separators=(",", ":")))
        .replace("__TOTAL__", str(len(events)))
    )
    OUT_PATH.write_text(html)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
