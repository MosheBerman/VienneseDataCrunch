#!/usr/bin/env python3
"""Build the Transport 1 transcription review page.

For every page: deskew + crop + line bands (same geometry as the OCR
run). Each band's NUMBER zone is OCR'd with a digit whitelist and the
band is matched to a transcription row by list number (exact, else a
unique Hamming-1 neighbour). Matched bands are saved as row crops;
rows without a matching band get no crop (the page shows the OCR text
only), bands without a row are listed as unassigned at the page end.

Outputs (in transcription/review/):
  crops/row-<list_no>.jpg   one crop per matched row
  data.json                 rows + crop paths for the page script
  index.html                the review page (written by build_html)

Crops are scan derivatives: the transports .gitignore already covers
**/*.jpg under transports/, so nothing here enters the public repo.
"""
import csv
import json
import sys
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ocr_pilot import crop_table, normalize_number  # noqa: E402
from rowbox_ocr import deskew, find_lines  # noqa: E402
from repair_pass import ocr_zone  # noqa: E402

REVIEW = HERE / "review"
CROPS = REVIEW / "crops"
TRANSCRIPTION = HERE.parent / "transport-01_transcription.csv"


def main():
    CROPS.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(TRANSCRIPTION.open()))
    by_no = {int(r["list_no"]): r for r in rows}
    pages = sorted({int(r["page"]) for r in rows})
    crop_of = {}
    unassigned = []

    for page in pages:
        srcs = sorted((HERE.parent).glob(f"page-{page:02d}_*.jpg"))
        img = cv2.imread(str(srcs[0]), cv2.IMREAD_GRAYSCALE)
        table = crop_table(deskew(img))
        w = table.shape[1]
        page_rows = sorted(n for n, r in by_no.items()
                           if int(r["page"]) == page)
        bands = find_lines(table)
        # Pass 1: anchor bands to rows by number-zone OCR (exact or a
        # unique Hamming-1 neighbour within this page's rows).
        anchors = {}  # band index -> list_no
        used = set()
        band_digits = []
        for bi, (y0, y1) in enumerate(bands):
            band = table[max(0, y0 - 6): y1 + 6, :]
            # number zone: sheets differ in left margin (page 1 numbers sit
            # at ~0.02-0.10 of crop width, page 20 at ~0.13-0.20), so take a
            # wide slice; the digit whitelist keeps surname letters out.
            num_txt = ocr_zone(band[:, : int(0.22 * w)], "0123456789.")
            digits = "".join(c for c in num_txt if c.isdigit())
            band_digits.append(digits)
            no = int(digits) if digits else None
            if no in page_rows and no not in used:
                anchors[bi] = no
                used.add(no)
            elif no is not None:
                cands = [n for n in page_rows
                         if n not in used and len(str(n)) == len(digits)
                         and sum(a != b for a, b in zip(str(n), digits)) == 1]
                if len(cands) == 1:
                    anchors[bi] = cands[0]
                    used.add(cands[0])
        # Pass 2: monotone interpolation. Rows and bands are both in page
        # order, so between two anchors the leftover rows and bands zip
        # together in order; before the first / after the last anchor the
        # same holds from the page edges.
        matched = dict(anchors)
        points = [(-1, None)] + sorted(anchors.items()) + \
                 [(len(bands), None)]
        for (b0, n0), (b1, n1) in zip(points, points[1:]):
            seg_bands = list(range(b0 + 1, b1))
            seg_rows = [n for n in page_rows
                        if (n0 is None or n > n0) and (n1 is None or n < n1)
                        and n not in used]
            for bi, n in zip(seg_bands, seg_rows):
                matched[bi] = n
                used.add(n)
        for bi, (y0, y1) in enumerate(bands):
            band = table[max(0, y0 - 6): y1 + 6, :]
            if bi in matched:
                target = matched[bi]
                out = CROPS / f"row-{target}.jpg"
                cv2.imwrite(str(out), band,
                            [cv2.IMWRITE_JPEG_QUALITY, 82])
                crop_of[target] = f"crops/row-{target}.jpg"
            else:
                out = CROPS / f"unassigned-p{page:02d}-{bi:02d}.jpg"
                cv2.imwrite(str(out), band,
                            [cv2.IMWRITE_JPEG_QUALITY, 82])
                unassigned.append(
                    {"page": page, "crop": f"crops/{out.name}",
                     "zone_number": band_digits[bi]})
        print(f"page {page:02d}: {len(used)}/{len(page_rows)} rows cropped "
              f"({len(anchors)} by number, rest by order)")

    data = {
        "rows": [
            {**r, "crop": crop_of.get(int(r["list_no"]), "")}
            for r in sorted(rows, key=lambda r: int(r["list_no"]))
        ],
        "unassigned": unassigned,
    }
    payload = json.dumps(data, ensure_ascii=False)
    (REVIEW / "data.json").write_text(payload)
    # data.js twin: file:// pages cannot fetch() JSON, but a script tag works
    (REVIEW / "data.js").write_text(f"const DATA = {payload};")
    print(f"total crops: {len(crop_of)} / {len(rows)} rows; "
          f"unassigned bands: {len(unassigned)}")


if __name__ == "__main__":
    main()
