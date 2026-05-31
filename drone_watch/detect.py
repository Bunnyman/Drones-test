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
