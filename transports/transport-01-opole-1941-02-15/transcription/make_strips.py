#!/usr/bin/env python3
"""Band-strip contact images: left part of each page's table with red
band lines and blue band indices, for visual verification of the
band-truth table. Usage: python3 make_strips.py 2 3 4 ..."""
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ocr_pilot import crop_table  # noqa: E402
from rowbox_ocr import deskew, find_lines  # noqa: E402

PAGES_DIR = HERE.parent


def strip(page):
    src = sorted(PAGES_DIR.glob(f"page-{page:02d}_*.jpg"))[0]
    img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    d = deskew(img)
    table = crop_table(d)
    bands = find_lines(table)
    vis = cv2.cvtColor(table, cv2.COLOR_GRAY2BGR)
    for i, (y0, y1) in enumerate(bands):
        cv2.line(vis, (0, y0), (vis.shape[1], y0), (0, 0, 255), 2)
        cv2.putText(vis, str(i), (8, y0 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
    # Left 45% only (number + surname), full height, scaled to width 1100.
    w = int(vis.shape[1] * 0.45)
    left = vis[:, :w]
    scale = 1100 / left.shape[1]
    out = cv2.resize(left, None, fx=scale, fy=scale,
                     interpolation=cv2.INTER_AREA)
    path = HERE / "out" / f"bandstrip-p{page:02d}.png"
    cv2.imwrite(str(path), out)
    print(page, len(bands), "bands ->", path, out.shape)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        strip(int(p))
