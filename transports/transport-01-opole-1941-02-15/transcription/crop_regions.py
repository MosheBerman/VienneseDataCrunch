#!/usr/bin/env python3
"""Targeted band-region crops for visual verification.
Usage: python3 crop_regions.py p2:34-38 p3:7-12 ...
Writes out/region-p<page>-b<lo>-<hi>.png (left 45% of table, band
lines + indices, full strip resolution)."""
import sys
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ocr_pilot import crop_table  # noqa: E402
from rowbox_ocr import deskew, find_lines  # noqa: E402

PAGES_DIR = HERE.parent


def region(page, lo, hi):
    src = sorted(PAGES_DIR.glob(f"page-{page:02d}_*.jpg"))[0]
    img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    table = crop_table(deskew(img))
    bands = find_lines(table)
    vis = cv2.cvtColor(table, cv2.COLOR_GRAY2BGR)
    for i, (y0, y1) in enumerate(bands):
        cv2.line(vis, (0, y0), (vis.shape[1], y0), (0, 0, 255), 2)
        cv2.putText(vis, str(i), (8, y0 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
    y_top = max(0, bands[lo][0] - 15)
    y_bot = min(vis.shape[0], bands[hi][1] + 15)
    w = int(vis.shape[1] * 0.45)
    crop = vis[y_top:y_bot, :w]
    path = HERE / "out" / f"region-p{page:02d}-b{lo:02d}-{hi:02d}.png"
    cv2.imwrite(str(path), crop)
    print(path, crop.shape)


if __name__ == "__main__":
    for spec in sys.argv[1:]:
        pg, rng = spec.split(":")
        lo, hi = rng.split("-")
        region(int(pg[1:]), int(lo), int(hi))
