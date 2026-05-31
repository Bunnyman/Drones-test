"""SQLite storage for parsed drone detections, with per-file dedup."""

import hashlib
import os
import sqlite3
from datetime import datetime, timezone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    path          TEXT NOT NULL,
    sha256        TEXT NOT NULL UNIQUE,
    processed_at  TEXT NOT NULL,
    num_detections INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS detections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id       INTEGER NOT NULL REFERENCES processed_files(id),
    source_image  TEXT NOT NULL,
    drone_type    TEXT,
    track_id      TEXT,
    raw_number    TEXT,
    value_num     INTEGER,
    detected_time TEXT,
    pixel_x       INTEGER,
    pixel_y       INTEGER,
    lat           REAL,
    lon           REAL,
    ocr_text      TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_detections_track ON detections(track_id);
CREATE INDEX IF NOT EXISTS idx_detections_time  ON detections(detected_time);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def connect(db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def file_already_processed(conn, sha):
    cur = conn.execute("SELECT 1 FROM processed_files WHERE sha256 = ?", (sha,))
    return cur.fetchone() is not None


def record_file(conn, path, sha, num_detections):
    cur = conn.execute(
        "INSERT INTO processed_files (path, sha256, processed_at, num_detections) "
        "VALUES (?, ?, ?, ?)",
        (path, sha, _now(), num_detections),
    )
    return cur.lastrowid


def insert_detection(conn, file_id, source_image, fields, pixel, lonlat):
    lon, lat = (lonlat if lonlat else (None, None))
    conn.execute(
        "INSERT INTO detections (file_id, source_image, drone_type, track_id, "
        "raw_number, value_num, detected_time, pixel_x, pixel_y, lat, lon, "
        "ocr_text, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            file_id,
            source_image,
            fields.get("drone_type"),
            fields.get("track_id"),
            fields.get("raw_number"),
            fields.get("value_num"),
            fields.get("detected_time"),
            pixel[0],
            pixel[1],
            lat,
            lon,
            fields.get("ocr_text"),
            _now(),
        ),
    )
