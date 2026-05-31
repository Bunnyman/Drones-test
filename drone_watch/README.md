# drone_watch

Watches a local folder for new map screenshots, parses the **red drone dots**
(FPV markers) out of each image, georeferences them to lat/long, and appends
the results to a local **SQLite** database. Driven by **cron**.

Pipeline: `detect` (OpenCV red-dot detection) → `ocr` (Tesseract reads the
label) → `parse` (regex → type / track ID / number / timestamp) → `georef`
(affine pixel→lat/long) → `db` (SQLite, deduped by file hash).

> Only red markers are treated as drones, matching the rule *"the drone is the
> red dot"*. Black crosshair / fixed-wing recon icons are ignored.

## Install (on your own machine)

```bash
# 1. system dependency: Tesseract OCR + Ukrainian language data
#    Debian/Ubuntu:
sudo apt-get install tesseract-ocr tesseract-ocr-ukr
#    macOS (Homebrew):
brew install tesseract tesseract-lang

# 2. python deps
pip install -r drone_watch/requirements.txt

# 3. config
cp drone_watch/config.example.json drone_watch/config.json
```

## Run

```bash
# process any new screenshots once and exit (this is what cron calls)
python -m drone_watch.watch --once

# or poll the folder continuously (no cron needed)
python -m drone_watch.watch --watch --interval 60
```

Drop `.png`/`.jpg` screenshots into the `incoming/` folder (configurable).
Each run hashes every file; already-seen files are skipped, so re-running is
safe. Processed files are moved to `processed/` if `move_processed` is true.

## Cron

Edit `drone_watch/crontab.example` (set absolute paths), then:

```bash
crontab -e        # paste the line
crontab -l        # verify
```

It runs every 2 minutes and logs to `drone_watch/cron.log`.

## Calibration (important for accurate coordinates)

`georef` uses a **fixed affine transform** built from control points in
`calibration.json`. This only works if your screenshots all use the **same map
source, crop, and zoom level**.

The shipped control points were eyeballed from one example image and are only
good to a few km. **Recalibrate for your setup:**

1. Open a representative screenshot in any image editor.
2. For 4–7 labelled towns, note the exact pixel `(x, y)` and look up the real
   `[lon, lat]` (e.g. from OpenStreetMap).
3. Put them in `calibration.json`.
4. Check the fit:
   ```bash
   python -m drone_watch.calibrate_check
   ```
   Aim for residuals well under 1 km. If the map view changes between
   screenshots, fixed calibration won't work — you'd need per-image control
   points (e.g. the Claude-vision parser option).

## Querying the data

```sql
-- everything, newest first
SELECT source_image, drone_type, track_id, raw_number, detected_time,
       round(lat,5) AS lat, round(lon,5) AS lon
FROM detections ORDER BY id DESC;

-- track one drone's sightings over time
SELECT detected_time, lat, lon FROM detections
WHERE track_id = '4872' ORDER BY detected_time;
```

```bash
sqlite3 drones.db "SELECT * FROM detections LIMIT 20;"
```

## Schema

- `processed_files(id, path, sha256 UNIQUE, processed_at, num_detections)`
- `detections(id, file_id, source_image, drone_type, track_id, raw_number,
  value_num, detected_time, pixel_x, pixel_y, lat, lon, ocr_text, created_at)`

## Tuning detection

If dots are missed or extra blobs appear, adjust in `config.json`:

- `red_hsv_ranges` — HSV bands for "red" (two bands cover the hue wraparound).
- `min_dot_area` / `max_dot_area` — blob size filter in pixels².
- `label_box_dx/_offset_y/_w/_h` — position/size of the text crop relative to
  each dot. Tweak if OCR grabs the wrong region.

## Limitations

- Accuracy of coordinates is bounded by calibration quality (see above).
- OCR on small/overlapping labels is imperfect; every field is best-effort and
  may be `NULL`. The raw OCR text is stored in `detections.ocr_text` for audit.
- Tested logic (parse, georef, db) has unit tests in `tests/`; the CV/OCR
  stages need the real binaries and are exercised at runtime.

## Tests

```bash
python drone_watch/tests/test_parse.py
python drone_watch/tests/test_pipeline.py
```
