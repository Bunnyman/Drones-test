"""Folder-watch entry point: scan for new screenshots, parse drone data, store.

Designed to be driven by cron with `--once` (process new files and exit), or
run standalone with `--watch` (poll forever).

    python -m drone_watch.watch --once --config drone_watch/config.json
"""

import argparse
import json
import os
import shutil
import sys
import time

from . import db, parse
from .georef import Georeferencer

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def load_config(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def iter_images(folder):
    for name in sorted(os.listdir(folder)):
        if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
            yield os.path.join(folder, name)


def process_image(path, conn, geo, cfg):
    """Process one screenshot; returns number of detections inserted."""
    import cv2  # local imports so cron/empty runs don't require opencv
    from . import detect, ocr

    sha = db.sha256_file(path)
    if db.file_already_processed(conn, sha):
        return -1  # signal "skipped"

    image = cv2.imread(path)
    if image is None:
        print(f"  ! could not read {path}", file=sys.stderr)
        return 0

    dots = detect.detect_markers(image, cfg)
    detections = []
    for dot in dots:
        crop = detect.label_crop(image, dot, cfg)
        text = ocr.ocr_region(crop, cfg)
        fields = parse.parse_label(text)
        lonlat = geo.to_lonlat(*dot["pixel"]) if geo else None
        detections.append((fields, dot["pixel"], lonlat))

    file_id = db.record_file(conn, path, sha, len(detections))
    src = os.path.basename(path)
    for fields, pixel, lonlat in detections:
        db.insert_detection(conn, file_id, src, fields, pixel, lonlat)
    conn.commit()
    return len(detections)


def run_once(cfg, conn, geo):
    total_files = 0
    total_dets = 0
    for path in iter_images(cfg["watch_dir"]):
        n = process_image(path, conn, geo, cfg)
        if n == -1:
            continue  # already processed
        total_files += 1
        total_dets += n
        print(f"  parsed {os.path.basename(path)}: {n} drone(s)")
        if cfg.get("move_processed") and cfg.get("processed_dir"):
            os.makedirs(cfg["processed_dir"], exist_ok=True)
            shutil.move(path, os.path.join(cfg["processed_dir"],
                                           os.path.basename(path)))
    print(f"done: {total_files} new file(s), {total_dets} detection(s)")
    return total_files


def main(argv=None):
    ap = argparse.ArgumentParser(description="Parse drone screenshots into SQLite")
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(__file__), "config.json"))
    ap.add_argument("--once", action="store_true",
                    help="process new files once and exit (use this from cron)")
    ap.add_argument("--watch", action="store_true",
                    help="poll the folder forever")
    ap.add_argument("--interval", type=int, default=60,
                    help="poll interval in seconds for --watch")
    args = ap.parse_args(argv)

    if not os.path.exists(args.config):
        sys.exit(f"config not found: {args.config} "
                 f"(copy config.example.json to config.json)")
    cfg = load_config(args.config)
    os.makedirs(cfg["watch_dir"], exist_ok=True)

    conn = db.connect(cfg["database"])
    geo = None
    if cfg.get("calibration") and os.path.exists(cfg["calibration"]):
        geo = Georeferencer.from_file(cfg["calibration"])

    if args.watch:
        print(f"watching {cfg['watch_dir']} every {args.interval}s ...")
        while True:
            run_once(cfg, conn, geo)
            time.sleep(args.interval)
    else:
        run_once(cfg, conn, geo)


if __name__ == "__main__":
    main()
