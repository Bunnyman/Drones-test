import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from drone_watch.parse import parse_label


def test_basic_fpv():
    text = "FPV / 4872\n-, 3880/1, -\n19:47:21"
    r = parse_label(text)
    assert r["drone_type"] == "FPV"
    assert r["track_id"] == "4872"
    assert r["raw_number"] == "3880/1"
    assert r["value_num"] == 3880
    assert r["detected_time"] == "19:47:21"


def test_multiword_type():
    r = parse_label("FPV крило / 4834\n-, 5474/1, -\n19:48:12")
    assert r["drone_type"] == "FPV крило"
    assert r["track_id"] == "4834"
    assert r["value_num"] == 5474


def test_oko_type():
    r = parse_label("FPVоко8 / 4845\n-, 5528/1, -\n19:46:30")
    assert r["drone_type"] == "FPVоко"
    assert r["track_id"] == "4845"


def test_noisy_ocr_partial():
    # garbled timestamp, missing slash-number
    r = parse_label("FPV / 4871\nsome noise")
    assert r["track_id"] == "4871"
    assert r["detected_time"] is None
    assert r["value_num"] is None


def test_empty():
    r = parse_label("")
    assert r["track_id"] is None
    assert r["drone_type"] is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all parse tests passed")
