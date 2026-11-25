#!/usr/bin/env python3
"""OCR pilot for Transport 1 list pages (typed lists, Tesseract, cheapest first).

Variants:
  vanilla      - tesseract deu, psm 6, straight on the JPEG
  otsu         - grayscale + Otsu binarization
  otsu2x       - Otsu + 2x upscale (typewriter glyphs are small at 300dpi)
  adapt        - adaptive Gaussian threshold (uneven background / show-through)
  clahe_otsu   - CLAHE contrast boost, then Otsu

Each variant's raw text is saved next to this script under out/<variant>/.
With --eval and ground_truth_page01.csv present, page-01 output is parsed
into rows and scored against the ground truth (row recall + name/date CER).

Usage:
  python3 ocr_pilot.py [--pages 1 2 3] [--variants vanilla otsu ...] [--eval]
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
OUT = HERE / "out"

DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[.,]\s?(\d{1,2})[.,]\s?(\d{4})(?!\d)")
DATE3_RE = re.compile(r"(?<!\d)(\d{2})\d[.,]\s?(\d{1,2})[.,]\s?(\d{4})(?!\d)")
ROW_RE = re.compile(r"^\s*(\d{1,4})\s*[.,]?\s+(.+?)\s*$")
CONFUSE = str.maketrans({"l": "1", "I": "1", "|": "1", "O": "0", "o": "0",
                         "S": "5", "s": "5", "B": "8", "Z": "2", "G": "6"})


def normalize_number(tok: str):
    t = tok.translate(CONFUSE)
    return int(t) if t.isdigit() else None


DATE_LOOSE_RE = re.compile(r"(?<!\d)(\d{1,2})\D{1,3}(\d{1,2})\D{1,3}(\d{4})(?!\d)")


def _valid(d, mo, y):
    return 1 <= d <= 31 and 1 <= mo <= 12 and 1800 <= y <= 1950


def parse_date(text: str):
    """Return (iso_date, matched_string) or (None, None). Validates ranges;
    falls back to looser patterns for OCR-mangled separators and digits."""
    m = DATE_RE.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid(d, mo, y):
            return f"{y:04d}-{mo:02d}-{d:02d}", m.group(0)
        # month like 17 from "7." with a stray leading 1: drop first digit
        if 13 <= mo <= 19 and _valid(d, mo - 10, y):
            return f"{y:04d}-{mo - 10:02d}-{d:02d}", m.group(0)
    m = DATE3_RE.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid(d, mo, y):
            return f"{y:04d}-{mo:02d}-{d:02d}", m.group(0)
    m = DATE_LOOSE_RE.search(text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid(d, mo, y):
            return f"{y:04d}-{mo:02d}-{d:02d}", m.group(0)
    return None, None


def preprocess(img: np.ndarray, variant: str) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if variant == "otsu":
        _, out = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return out
    if variant == "otsu2x":
        big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, out = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return out
    if variant == "adapt":
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 15
        )
    if variant == "clahe_otsu":
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        eq = clahe.apply(gray)
        _, out = cv2.threshold(eq, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return out
    raise ValueError(variant)


def crop_table(img: np.ndarray) -> np.ndarray:
    """Cut to the table area, dropping the frame edges and margin noise lines.

    Fractions measured on page 1 (2515x3496): outer frame lines sit at
    x~0.13/0.90 and y~0.08/0.96 of the page; the list text lives inside.
    """
    h, w = img.shape[:2]
    return img[int(0.095 * h):int(0.955 * h), int(0.16 * w):int(0.90 * w)]


def run_tesseract(image_path: Path, psm: int = 6) -> str:
    res = subprocess.run(
        ["tesseract", str(image_path), "stdout", "-l", "deu", "--psm", str(psm)],
        capture_output=True, text=True, timeout=300,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr[:500])
    return res.stdout


LEAD_TOK_RE = re.compile(r"^\s*\S{0,3}?([0-9lIOoSsBZG]{1,4})\s*[.,]")


def parse_rows(text: str, start_no: int = 1):
    """Parse using the PRINTED list number (with OCR digit-confusion
    normalization) as the primary key, the expected counter as fallback.
    A line is a row if it carries a birth date or a plausible printed
    number near the expected counter. Gaps (numbers skipped by OCR line
    segmentation) are recorded as flags, never silently renumbered."""
    rows = []
    expected = start_no
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        date, dstr = parse_date(s)
        m = LEAD_TOK_RE.match(s)
        lead = normalize_number(m.group(1)) if m else None
        if date is None and lead is None:
            continue
        flags = []
        if lead is not None and start_no <= lead <= start_no + 200:
            no = lead
            if lead > expected:
                flags.append(f"gap_before:{expected}-{lead - 1}")
            elif lead < expected:
                flags.append("number_out_of_order")
        elif date is not None:
            no = expected
            flags.append("number_inferred")
        else:
            continue
        seg = s[m.end():] if m else s
        if dstr and dstr in seg:
            seg = seg[: seg.find(dstr)]
        name = seg.strip(" .|")
        name = re.sub(r"^[^A-ZÄÖÜa-zäöüß]{1,3}\s+", "", name)  # lead junk token
        rows.append(
            {"list_no": no, "name_raw": name, "birth_date": date,
             "flags": ";".join(flags), "line": line}
        )
        expected = no + 1
    return rows


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def evaluate(rows, gt_rows):
    gt = {int(r["list_no"]): r for r in gt_rows}
    got = {r["list_no"]: r for r in rows if r["list_no"] in gt}
    name_err = date_err = 0
    name_len = date_len = 0
    misses = []
    for no, g in sorted(gt.items()):
        if no not in got:
            misses.append(no)
            name_err += len(g["surname"]) + 1 + len(g["given_names"])
            name_len += len(g["surname"]) + 1 + len(g["given_names"])
            date_err += len(g["birth_date"])
            date_len += len(g["birth_date"])
            continue
        want = f"{g['surname']} {g['given_names']}".upper()
        have = got[no]["name_raw"].upper()
        name_err += levenshtein(want, have)
        name_len += len(want)
        want_d = g["birth_date"] or ""
        have_d = got[no]["birth_date"] or ""
        date_err += levenshtein(want_d, have_d)
        date_len += len(want_d)
    return {
        "rows_found": len(got),
        "rows_total": len(gt),
        "missing": misses,
        "name_cer": name_err / name_len if name_len else 1.0,
        "date_cer": date_err / date_len if date_len else 1.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, nargs="+", default=[1])
    ap.add_argument(
        "--variants", nargs="+",
        default=["vanilla", "otsu", "otsu2x", "adapt", "clahe_otsu"],
    )
    ap.add_argument("--eval", action="store_true")
    args = ap.parse_args()

    gt_rows = []
    gt_path = HERE / "ground_truth_page01.csv"
    if args.eval and gt_path.exists():
        gt_rows = list(csv.DictReader(gt_path.open()))

    for variant in args.variants:
        vdir = OUT / variant
        vdir.mkdir(parents=True, exist_ok=True)
        for page in args.pages:
            src = sorted(PAGES_DIR.glob(f"page-{page:02d}_*.jpg"))
            if not src:
                print(f"page {page}: no image found", file=sys.stderr)
                continue
            src = src[0]
            psm = 4 if variant.endswith("_p4") else 6
            base = variant[:-3] if variant.endswith("_p4") else variant
            if base == "vanilla":
                work = src
            elif base.startswith("crop"):
                img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
                proc = crop_table(img)
                if base == "crop_otsu":
                    _, proc = cv2.threshold(
                        proc, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )
                elif base == "crop2x":
                    proc = cv2.resize(proc, None, fx=2, fy=2,
                                      interpolation=cv2.INTER_CUBIC)
                work = vdir / f"page-{page:02d}_prep.png"
                cv2.imwrite(str(work), proc)
            else:
                img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
                proc = preprocess(img, base)
                work = vdir / f"page-{page:02d}_prep.png"
                cv2.imwrite(str(work), proc)
            text = run_tesseract(work, psm=psm)
            (vdir / f"page-{page:02d}.txt").write_text(text)
            rows = parse_rows(text)
            print(f"[{variant}] page {page:02d}: {len(rows)} rows parsed")
            if args.eval and page == 1 and gt_rows:
                ev = evaluate(rows, gt_rows)
                print(
                    f"    GT eval: rows {ev['rows_found']}/{ev['rows_total']}"
                    f" missing={ev['missing']}"
                    f" name CER {ev['name_cer']:.3f} date CER {ev['date_cer']:.3f}"
                )


if __name__ == "__main__":
    main()
