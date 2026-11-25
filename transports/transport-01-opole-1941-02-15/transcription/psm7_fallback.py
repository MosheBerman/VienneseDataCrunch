#!/usr/bin/env python3
"""Fallback single-line OCR for bands the stack pass read poorly.

Runs tesseract psm 7 on the crop file of every band whose stack OCR
was empty or unparseable. Serial, one call at a time (sandbox CPU cap
makes parallel per-crop OCR impractical).

Page 5 uses the wide re-cut slices (numbers visible).
Output: out/band_psm7.csv (page, band_index, psm7_text)
"""
import csv
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROPS = HERE / "review" / "crops"
WIDE = HERE / "review" / "crops_wide"
OUT = HERE / "out" / "band_psm7.csv"


def main():
    rows = list(csv.DictReader(open(HERE / "out" / "band_numbers.csv")))
    targets = [r for r in rows if r["status"] in ("unclear", "none")]
    print(f"{len(targets)} bands to re-read")
    out = []
    for i, r in enumerate(targets):
        page = int(r["page"])
        band = int(r["band_index"])
        if page == 5:
            img = WIDE / f"p05-{band:02d}.jpg"
        else:
            img = CROPS / r["crop_file"]
        p = subprocess.run(
            ["tesseract", str(img), "stdout", "-l", "deu", "--psm", "7"],
            capture_output=True, text=True, timeout=60)
        text = " ".join(p.stdout.split())
        out.append([page, band, text])
        if i % 50 == 0:
            print(i, "done")
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page", "band_index", "psm7_text"])
        w.writerows(out)
    print("wrote", OUT, len(out), "rows")


if __name__ == "__main__":
    main()
