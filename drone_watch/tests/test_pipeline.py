"""Tests for georef + db that don't require OpenCV/Tesseract."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from drone_watch import db
from drone_watch.georef import Georeferencer
from drone_watch.parse import parse_label


def test_georef_recovers_control_points():
    # a perfect affine grid: lon = 0.01*x, lat = 50 - 0.01*y
    pts = [
        {"name": "a", "pixel": [0, 0], "lonlat": [0.0, 50.0]},
        {"name": "b", "pixel": [100, 0], "lonlat": [1.0, 50.0]},
        {"name": "c", "pixel": [0, 100], "lonlat": [0.0, 49.0]},
        {"name": "d", "pixel": [100, 100], "lonlat": [1.0, 49.0]},
    ]
    geo = Georeferencer(pts)
    lon, lat = geo.to_lonlat(50, 50)
    assert abs(lon - 0.5) < 1e-9
    assert abs(lat - 49.5) < 1e-9
    assert max(e for _, e in geo.residuals_m()) < 1.0


def test_db_roundtrip_and_dedup():
    with tempfile.TemporaryDirectory() as d:
        dbpath = os.path.join(d, "test.db")
        conn = db.connect(dbpath)

        # fake an image file to hash
        img = os.path.join(d, "shot.png")
        with open(img, "wb") as fh:
            fh.write(b"fake-image-bytes")
        sha = db.sha256_file(img)

        assert not db.file_already_processed(conn, sha)
        fields = parse_label("FPV / 4872\n-, 3880/1, -\n19:47:21")
        file_id = db.record_file(conn, img, sha, 1)
        db.insert_detection(conn, file_id, "shot.png", fields,
                            (917, 170), (37.71, 49.64))
        conn.commit()

        assert db.file_already_processed(conn, sha)
        row = conn.execute(
            "SELECT track_id, value_num, lat, lon FROM detections").fetchone()
        assert row["track_id"] == "4872"
        assert row["value_num"] == 3880
        assert abs(row["lat"] - 49.64) < 1e-9


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all pipeline tests passed")
