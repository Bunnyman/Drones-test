"""Ingest drone screenshots from a JSON array of base64-encoded images.

Input JSON: a list of objects like
    {"Id": "...", "Image": "<base64 PNG>", "TimestampUtc": "2026-02-16T14:53:27Z"}

For each image we detect drone markers (red dots / FPV badges), georeference
them with the configured calibration, and insert rows into the SQLite DB. The
per-image `TimestampUtc` is stored as each detection's detected_time (these
map frames carry no per-marker time label).

    python -m drone_watch.ingest_json path/to/images.json --config drone_watch/config.json

Dedup: a SHA-256 of each image's bytes is recorded, so re-running skips images
already ingested.
"""

import argparse
import base64
import hashlib
import json
import os
import sys

import cv2
import numpy as np

from . import db, detect
from .georef import Georeferencer
from .watch import load_config


def _decode(b64):
    raw = base64.b64decode(b64)
    arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return raw, img


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingest base64 images JSON into the DB")
    ap.add_argument("json_path")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config.json"))
    ap.add_argument("--image-key", default="Image")
    ap.add_argument("--time-key", default="TimestampUtc")
    ap.add_argument("--id-key", default="Id")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    conn = db.connect(cfg["database"])
    geo = None
    if cfg.get("calibration") and os.path.exists(cfg["calibration"]):
        geo = Georeferencer.from_file(cfg["calibration"])

    with open(args.json_path, "r", encoding="utf-8") as fh:
        items = json.load(fh)

    total_det = 0
    skipped = 0
    for i, item in enumerate(items):
        raw, img = _decode(item[args.image_key])
        sha = hashlib.sha256(raw).hexdigest()
        if db.file_already_processed(conn, sha):
            skipped += 1
            continue
        img_id = item.get(args.id_key, f"item{i}")
        ts = item.get(args.time_key)
        src = f"{img_id}.png"

        dots = detect.detect_markers(img, cfg) if img is not None else []
        file_id = db.record_file(conn, src, sha, len(dots))
        for dot in dots:
            lonlat = geo.to_lonlat(*dot["pixel"]) if geo else None
            fields = {"drone_type": "FPV", "track_id": None, "raw_number": None,
                      "value_num": None, "detected_time": ts, "ocr_text": None}
            db.insert_detection(conn, file_id, src, fields, dot["pixel"], lonlat)
        total_det += len(dots)
        print(f"  {src}: {len(dots)} marker(s)  ts={ts}")
    conn.commit()
    print(f"done: {len(items)-skipped} ingested, {skipped} already present, "
          f"{total_det} detections")


if __name__ == "__main__":
    main()
