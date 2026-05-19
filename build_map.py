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
    <span>Aggregated events: <span id="count">0</span> / __TOTAL__
      across __DAYS__ days (__DATE_RANGE__)</span>
    <span style="flex:1"></span>
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
    <input id="slider" type="range" min="0" max="86340" value="0" step="60">
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
const windowSel = document.getElementById('window');
const playBtn = document.getElementById('play');

function fmtTod(secs) {
  secs = ((secs % 86400) + 86400) % 86400;
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
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
  const visible = EVENTS.filter(e => inWindow(e.tod));

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
}

slider.addEventListener('input', update);
windowSel.addEventListener('change', update);

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
