"""Parse the raw OCR text of a single marker label into structured fields.

A typical marker label reads (three lines):

    FPV / 4872
    -, 3880/1, -
    19:47:21

OCR is noisy, so every field is best-effort and may be None.
"""

import re

# drone type tokens seen on the map, longest first so multi-word wins
_TYPE_TOKENS = [
    "FPV крило",
    "FPVоко",
    "FPV око",
    "СКАТ",
    "SKAT",
    "FPV",
]

_TIME_RE = re.compile(r"\b([0-2]?\d:[0-5]\d:[0-5]\d)\b")
_SLASH_NUM_RE = re.compile(r"(\d{2,6})\s*/\s*(\d{1,3})")
_TRACK_RE = re.compile(r"/\s*(\d{3,5})")
_ANY4 = re.compile(r"\b(\d{4})\b")


def parse_label(text):
    """Return a dict with best-effort fields parsed from OCR `text`."""
    clean = " ".join(text.split())

    result = {
        "drone_type": None,
        "track_id": None,
        "raw_number": None,
        "value_num": None,
        "detected_time": None,
        "ocr_text": text.strip(),
    }

    # drone type
    for token in _TYPE_TOKENS:
        if token.lower() in clean.lower():
            result["drone_type"] = token
            break

    # timestamp HH:MM:SS
    m = _TIME_RE.search(clean)
    if m:
        result["detected_time"] = m.group(1)

    # the "<value>/<index>" field (e.g. 3880/1)
    m = _SLASH_NUM_RE.search(clean)
    if m:
        result["raw_number"] = f"{m.group(1)}/{m.group(2)}"
        result["value_num"] = int(m.group(1))

    # track id: prefer "<type> / <id>" pattern, else first standalone 4-digit
    m = _TRACK_RE.search(clean)
    if m:
        result["track_id"] = m.group(1)
    else:
        m = _ANY4.search(clean)
        if m:
            result["track_id"] = m.group(1)

    return result
