"""OCR a cropped label region with Tesseract.

Requires: pytesseract, opencv-python, numpy, and the Tesseract binary
(plus the `ukr` language data) installed on the host.
"""

import cv2
import numpy as np
import pytesseract


def ocr_region(crop_bgr, cfg):
    """Return the recognised text for a label crop (best effort)."""
    if crop_bgr is None or crop_bgr.size == 0:
        return ""

    # upscale for small text, grayscale, Otsu threshold -> crisp glyphs
    scale = cfg.get("ocr_upscale", 3)
    big = cv2.resize(crop_bgr, None, fx=scale, fy=scale,
                     interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    _, thr = cv2.threshold(gray, 0, 255,
                           cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # labels are dark text on light halo; invert if background is dark
    if np.mean(thr) < 127:
        thr = cv2.bitwise_not(thr)

    config = f"--oem 3 --psm 6 -l {cfg.get('tesseract_lang', 'ukr+eng')}"
    return pytesseract.image_to_string(thr, config=config)
