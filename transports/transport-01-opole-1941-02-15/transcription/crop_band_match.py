#!/usr/bin/env python3
"""Match every review crop file to its source band by pixels (no OCR).

Recomputes deskew + table crop + line bands per page (same code as
make_review.py), then finds, for each crop jpg, the band slice it was
cut from. Output: out/crop_band_match.csv with
crop, page, band_index, diff_best, diff_second, ambiguous.
"""
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ocr_pilot import crop_table  # noqa: E402
from rowbox_ocr import deskew, find_lines  # noqa: E402

REVIEW = HERE / "review"
CROPS = REVIEW / "crops"
OUT = HERE / "out" / "crop_band_match.csv"
W = 400  # match width


def thumb(img):
    h, w = img.shape[:2]
    return cv2.resize(img, (W, max(1, int(h * W / w))),
                      interpolation=cv2.INTER_AREA)


def main():
    # Build band slices per page.
    pages = {}
    for page in range(1, 31):
        srcs = sorted((HERE.parent).glob(f"page-{page:02d}_*.jpg"))
        img = cv2.imread(str(srcs[0]), cv2.IMREAD_GRAYSCALE)
        table = crop_table(deskew(img))
        bands = find_lines(table)
        slices = []
        for (y0, y1) in bands:
            sl = table[max(0, y0 - 6): y1 + 6, :]
            slices.append((y0, y1, thumb(sl)))
        pages[page] = slices
        print(f"page {page:02d}: {len(bands)} bands", flush=True)

    rows = list(csv.DictReader((HERE.parent / "transport-01_transcription.csv").open()))
    page_of_row = {int(r["list_no"]): int(r["page"]) for r in rows}

    jobs = []
    for p in sorted(CROPS.glob("row-*.jpg")):
        n = int(p.stem.split("-")[1])
        jobs.append((p, page_of_row.get(n)))
    for p in sorted(CROPS.glob("unassigned-*.jpg")):
        pg = int(p.stem.split("-")[1][1:])
        jobs.append((p, pg))

    results = []
    for p, pg in jobs:
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        t = thumb(img)
        th, tw = t.shape[:2]
        cands = []
        for page, slices in pages.items():
            for bi, (y0, y1, sl) in enumerate(slices):
                if abs(sl.shape[0] - th) > 3:
                    continue
                h = min(th, sl.shape[0])
                diff = float(np.mean(cv2.absdiff(
                    t[:h, :], sl[:h, :])))
                cands.append((diff, page, bi))
        cands.sort()
        (d1, pg1, bi1) = cands[0]
        d2 = cands[1][0] if len(cands) > 1 else 999.0
        results.append((p.name, pg1, bi1, round(d1, 2), round(d2, 2),
                        "AMBIG" if d2 - d1 < 5 else ""))
        if pg is not None and pg1 != pg:
            results[-1] = results[-1][:1] + (pg1, bi1, round(d1, 2),
                                             round(d2, 2), "PAGE-DIFF")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["crop", "page", "band_index", "diff_best",
                    "diff_second", "flag"])
        w.writerows(results)
    bad = [r for r in results if r[3] > 15]
    print(f"matched {len(results)} crops; {len(bad)} with diff>15: "
          f"{[r[0] for r in bad][:20]}")
    print(f"ambiguous: {sum(1 for r in results if 'AMBIG' in r[5])}, "
          f"page-diff: {sum(1 for r in results if 'PAGE-DIFF' in r[5])}")


if __name__ == "__main__":
    main()
