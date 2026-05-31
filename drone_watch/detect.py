"""Detect the red drone dots on a screenshot using OpenCV colour thresholding.

Only *red* markers are returned, matching the rule "the drone is the red dot".
Other marker colours (black crosshair, fixed-wing recon icons) are ignored.

Requires: opencv-python, numpy.
"""

import cv2
import numpy as np


def detect_red_dots(image_bgr, cfg):
    """Return a list of dicts: {"pixel": (cx, cy), "bbox": (x, y, w, h)}.

    cfg keys used: red_hsv_ranges, min_dot_area, max_dot_area.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    mask = None
    for lo, hi in cfg["red_hsv_ranges"]:
        part = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        mask = part if mask is None else cv2.bitwise_or(mask, part)

    # close small gaps so the FPV glyph inside the circle doesn't split it
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    dots = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < cfg["min_dot_area"] or area > cfg["max_dot_area"]:
            continue
        x, y, w, h = cv2.boundingRect(c)
        # markers are roughly round; reject very elongated blobs (e.g. text)
        aspect = w / float(h) if h else 0
        if aspect < 0.4 or aspect > 2.5:
            continue
        dots.append({"pixel": (x + w // 2, y + h // 2), "bbox": (x, y, w, h)})

    # sort top-to-bottom, left-to-right for stable ordering
    dots.sort(key=lambda d: (d["pixel"][1], d["pixel"][0]))
    return dots


def detect_fpv_badges(image_bgr, cfg):
    """Detect 'FPV' badges rendered as a dark disk with a red/orange ring.

    Some map styles draw drone markers as a black circle (white "FPV" text)
    with a thin red ring rather than a solid red dot. This finds dark, roughly
    circular blobs that have red pixels around their border.

    cfg keys: badge_dark_max, badge_min_area, badge_max_area, badge_red_ring_min,
    plus red_hsv_ranges (reused for the ring test).
    Returns the same shape as detect_red_dots.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    dark = (gray < cfg.get("badge_dark_max", 70)).astype(np.uint8) * 255
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)

    red = None
    for lo, hi in cfg["red_hsv_ranges"]:
        part = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        red = part if red is None else cv2.bitwise_or(red, part)

    h_img, w_img = image_bgr.shape[:2]
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    badges = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < cfg.get("badge_min_area", 150) or area > cfg.get("badge_max_area", 1200):
            continue
        x, y, w, h = cv2.boundingRect(c)
        if h == 0 or not (0.6 <= w / float(h) <= 1.7):
            continue
        x0, y0 = max(0, x - 6), max(0, y - 6)
        x1, y1 = min(w_img, x + w + 6), min(h_img, y + h + 6)
        ring = red[y0:y1, x0:x1].sum() / 255
        if ring < cfg.get("badge_red_ring_min", 120):
            continue
        badges.append({"pixel": (x + w // 2, y + h // 2), "bbox": (x, y, w, h)})
    badges.sort(key=lambda d: (d["pixel"][1], d["pixel"][0]))
    return badges


def detect_markers(image_bgr, cfg):
    """Detect drone markers: solid red dots and/or dark FPV badges.

    cfg["marker_style"]: "red" | "badge" | "both" (default "both").
    Nearby duplicates (within 12 px) are merged.
    """
    style = cfg.get("marker_style", "both")
    found = []
    if style in ("red", "both"):
        found += detect_red_dots(image_bgr, cfg)
    if style in ("badge", "both"):
        found += detect_fpv_badges(image_bgr, cfg)

    merged = []
    for d in found:
        cx, cy = d["pixel"]
        if any(abs(cx - m["pixel"][0]) < 12 and abs(cy - m["pixel"][1]) < 12 for m in merged):
            continue
        merged.append(d)
    return merged


def label_crop(image_bgr, dot, cfg):
    """Return the sub-image containing the text label below a dot."""
    h_img, w_img = image_bgr.shape[:2]
    cx, cy = dot["pixel"]
    _, _, _, bh = dot["bbox"]

    top = cy + bh // 2 + cfg["label_offset_y"]
    left = cx + cfg["label_box_dx"]
    box_w = cfg["label_box_w"]
    box_h = cfg["label_box_h"]

    left = max(0, left)
    top = max(0, top)
    right = min(w_img, left + box_w)
    bottom = min(h_img, top + box_h)
    return image_bgr[top:bottom, left:right]
