#!/usr/bin/env python3
"""Rowbox OCR for the Transport 1 typed lists.

Tesseract's own line segmentation drops/merges lines on these pages
(observed: row 26 of page 1 vanishes in psm 6 text and TSV output).
So: detect text lines ourselves via horizontal projection of the
binarized table crop, split tall bands at their ink valley, OCR each
line strip separately (psm 7), then parse with the printed-number
rules (digit-confusion normalization, Hamming-1 misread tolerance,
explicit gap flags - rows are never silently renumbered).

Usage:
  python3 rowbox_ocr.py [--pages 1 2 3] [--eval] [--outdir DIR]
Writes <outdir>/transport-01_rows.csv and per-page raw line dumps.
"""
import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
PAGES_DIR = HERE.parent
sys.path.insert(0, str(HERE))
from ocr_pilot import crop_table, parse_date, normalize_number  # noqa: E402

LEAD_TOK_RE = re.compile(r"^\s*\S{0,3}?([0-9lIOoSsBZG]{1,4})\s*[.,]")
CAPS_RE = re.compile(r"[A-ZÄÖÜ]{4,}")


def find_lines(gray: np.ndarray):
    """Return [(y0, y1)] text line bands from horizontal ink projection.
    Continuous vertical rules (frame edges, column lines) are masked out
    first - otherwise every pixel row carries ink and no gaps appear."""
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink2d = bw < 128
    # Project over the NAME column only: every data row has ink there and
    # the inter-line gaps are clean there (measured p10 = 0), unlike the
    # margin/date columns where rules and annotations bridge the gaps.
    w = gray.shape[1]
    ink = ink2d[:, int(0.13 * w): int(0.60 * w)].sum(axis=1)
    on = ink > 3
    bands = []
    y = 0
    while y < len(on):
        if on[y]:
            y0 = y
            gap = 0
            while y < len(on) and (on[y] or gap < 6):
                gap = 0 if on[y] else gap + 1
                y += 1
            bands.append([y0, y - gap])
        else:
            y += 1
    if not bands:
        return []
    heights = [b[1] - b[0] for b in bands]
    med = float(np.median(heights))
    out = []
    for y0, y1 in bands:
        h = y1 - y0
        if h > 1.6 * med:  # merged double line: split at ink valley
            seg = ink[y0:y1]
            lo = int(0.3 * h)
            hi = int(0.7 * h)
            cut = y0 + lo + int(np.argmin(seg[lo:hi]))
            out.append((y0, cut))
            out.append((cut, y1))
        else:
            out.append((y0, y1))
    return out


def deskew(gray: np.ndarray) -> np.ndarray:
    """Rotate the page so text lines are horizontal. The Transport 1 scans
    are skewed ~2 degrees: on page 1 the date column sits ~35px lower than
    the name column on the same printed row, so un-deskewed strips slice
    through dates. Angle found by maximizing projection sharpness."""
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = (bw < 128).astype(np.uint8)
    h, w = gray.shape
    cx, cy = w // 2, h // 2
    best_a, best_s = 0.0, -1.0
    for a in np.arange(-3.0, 3.01, 0.25):
        m = cv2.getRotationMatrix2D((cx, cy), float(a), 1.0)
        rot = cv2.warpAffine(ink, m, (w, h), flags=cv2.INTER_NEAREST)
        p = rot[:, int(0.30 * w): int(0.55 * w)].sum(axis=1).astype(np.float64)
        s = float((p * p).sum())
        if s > best_s:
            best_s, best_a = s, float(a)
    if abs(best_a) < 0.01:
        return gray
    m = cv2.getRotationMatrix2D((cx, cy), best_a, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC,
                          borderValue=255)


def _tess(path: Path, psm: int) -> str:
    res = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "deu", "--psm", str(psm)],
        capture_output=True, text=True, timeout=120,
    )
    return res.stdout.strip()


STRIP_PREP = "gray"  # or "otsu" (experiment flag, set from main)


def ocr_strip(strip: np.ndarray) -> str:
    """OCR one line strip. psm 7 first; if the result is not row-like
    (no date and no caps surname token - e.g. it came back empty, as
    happened to the DUBSKY row on page 1), retry with more padding and
    psm 6, then with an Otsu-binarized strip."""
    if STRIP_PREP == "otsu":
        _, strip = cv2.threshold(strip, 0, 255,
                                 cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    tmp = HERE / "out" / "_strip.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    padded = cv2.copyMakeBorder(strip, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)
    cv2.imwrite(str(tmp), padded)
    text = _tess(tmp, 7)
    if parse_date(text)[0] is not None or CAPS_RE.search(text):
        return text
    tall = cv2.copyMakeBorder(strip, 14, 14, 8, 8, cv2.BORDER_CONSTANT, value=255)
    cv2.imwrite(str(tmp), tall)
    text2 = _tess(tmp, 6)
    if len(text2) > len(text):
        text = text2
    if parse_date(text)[0] is None and not CAPS_RE.search(text):
        _, bw = cv2.threshold(strip, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bw = cv2.copyMakeBorder(bw, 10, 10, 8, 8, cv2.BORDER_CONSTANT, value=255)
        cv2.imwrite(str(tmp), bw)
        text3 = _tess(tmp, 7)
        if len(text3) > len(text):
            text = text3
    return text


def hamming1(a: int, b: int) -> bool:
    sa, sb = str(a), str(b)
    return len(sa) == len(sb) and sum(x != y for x, y in zip(sa, sb)) == 1


def parse_strip(text: str, expected: int):
    """Assign a list number to one OCR'd line. Returns (row, next_expected)
    or (None, expected) if the line is not a data row."""
    if "erzeichnis" in text:  # page header
        return None, expected
    date, dstr = parse_date(text)
    m = LEAD_TOK_RE.match(text.strip())
    lead = normalize_number(m.group(1)) if m else None
    if date is None and not CAPS_RE.search(text):
        return None, expected
    flags = []
    if lead is not None and lead == expected:
        no = lead
    elif lead is not None and lead == expected + 1:
        no = lead
        flags.append(f"gap_before:{expected}")
    elif lead is not None and hamming1(lead, expected):
        no = expected
        flags.append(f"number_misread:{lead}")
    elif date is not None or CAPS_RE.search(text):
        no = expected
        flags.append("number_inferred" if lead is None else f"number_misread:{lead}")
    else:
        return None, expected
    seg = text.strip()
    if m:
        seg = seg[m.end():]
    if dstr and dstr in seg:
        seg = seg[: seg.find(dstr)]
    name = re.sub(r"^[^A-ZÄÖÜa-zäöüß]{1,3}\s+", "", seg.strip(" .|"))
    if date is None:
        flags.append("date_missing")
    return (
        {"list_no": no, "name_raw": name.strip(), "birth_date": date,
         "flags": ";".join(flags), "line": text},
        no + 1,
    )


def process_page(page: int, start_no: int):
    srcs = sorted(PAGES_DIR.glob(f"page-{page:02d}_*.jpg"))
    if not srcs:
        raise FileNotFoundError(f"page {page}")
    img = cv2.imread(str(srcs[0]), cv2.IMREAD_GRAYSCALE)
    table = crop_table(deskew(img))
    rows = []
    expected = start_no
    raws = []
    for (y0, y1) in find_lines(table):
        strip = table[max(0, y0 - 4): y1 + 4, :]
        text = ocr_strip(strip)
        raws.append(text)
        row, expected = parse_strip(text, expected)
        if row:
            row["page"] = page
            rows.append(row)
    return rows, expected, raws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, nargs="+", default=[1])
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--prep", choices=["gray", "otsu"], default="gray")
    ap.add_argument("--outdir", default=str(HERE / "out" / "rowbox"))
    args = ap.parse_args()
    global STRIP_PREP
    STRIP_PREP = args.prep

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    start = 1
    for page in args.pages:
        rows, start, raws = process_page(page, start)
        (outdir / f"page-{page:02d}_lines.txt").write_text("\n".join(raws))
        print(f"page {page:02d}: {len(rows)} rows, next start {start}")
        all_rows.extend(rows)

    with open(outdir / "transport-01_rows.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["list_no", "page", "name_raw", "birth_date", "flags", "ocr_line"])
        for r in all_rows:
            w.writerow([r["list_no"], r["page"], r["name_raw"],
                        r["birth_date"] or "", r["flags"], r["line"]])

    if args.eval:
        from ocr_pilot import evaluate
        gt = list(csv.DictReader((HERE / "ground_truth_page01.csv").open()))
        p1 = [r for r in all_rows if r["page"] == 1]
        ev = evaluate(p1, gt)
        print(f"GT eval page 1: rows {ev['rows_found']}/{ev['rows_total']} "
              f"missing={ev['missing']} name CER {ev['name_cer']:.3f} "
              f"date CER {ev['date_cer']:.3f}")


if __name__ == "__main__":
    main()
