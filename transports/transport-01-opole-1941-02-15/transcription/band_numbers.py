#!/usr/bin/env python3
"""Recover the printed number of every band, one OCR call per page.

Stacks each page's band slices (the same slices the review crops were
cut from) with white separators, OCRs the stack once (Tesseract deu,
psm 6, TSV), and maps each OCR line back to its slice by y-coordinate.
Parsing uses the pipeline's own lead-token rule.

Output: out/band_numbers.csv with
page, band_index, crop_file, ocr_text, numbers, status
status: ok (one number), none (no number read), merged (two+ numbers),
unclear (number unparseable).
"""
import csv
import glob
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ocr_pilot import crop_table  # noqa: E402
from rowbox_ocr import deskew, find_lines  # noqa: E402

REVIEW = HERE / "review"
OUT = HERE / "out" / "band_numbers.csv"
SEP = 14

LEAD_TOK_RE = re.compile(r"^\s*\S{0,3}?([0-9lIOoSsBZG]{1,4})\s*[.,]")


def normalize_number(s):
    return (s.replace("l", "1").replace("I", "1").replace("O", "0")
             .replace("o", "0").replace("S", "5").replace("s", "5")
             .replace("B", "8").replace("Z", "2").replace("G", "6"))


def parse_number(text):
    m = LEAD_TOK_RE.match(text.strip())
    if not m:
        return None
    digits = normalize_number(m.group(1))
    return int(digits) if digits.isdigit() else None


def main():
    match = {}
    for r in csv.DictReader(open(HERE / "out" / "crop_band_match.csv")):
        match[(int(r["page"]), int(r["band_index"]))] = r["crop"]

    rows_out = []
    for page in range(1, 31):
        srcs = sorted(glob.glob(str(HERE.parent / f"page-{page:02d}_*.jpg")))
        img = cv2.imread(srcs[0], cv2.IMREAD_GRAYSCALE)
        table = crop_table(deskew(img))
        bands = find_lines(table)
        parts = []
        ranges = []  # (y_start, y_end) per band in stack coords
        y = 0
        for (y0, y1) in bands:
            sl = table[max(0, y0 - 6): y1 + 6, :]
            parts.append(sl)
            ranges.append((y, y + sl.shape[0]))
            y += sl.shape[0]
            parts.append(np.full((SEP, table.shape[1]), 255,
                                 dtype=np.uint8))
            y += SEP
        stack = np.vstack(parts)
        tmp = f"/tmp/stack-p{page:02d}.png"
        cv2.imwrite(tmp, stack)
        r = subprocess.run(
            ["tesseract", tmp, "stdout", "-l", "deu", "--psm", "6", "tsv"],
            capture_output=True, text=True, timeout=120)
        # Group words into lines by (block, par, line), keep y-center.
        lines = {}
        tsv = csv.DictReader(r.stdout.splitlines(), delimiter="\t",
                             quoting=csv.QUOTE_NONE)
        for w in tsv:
            if w["level"] != "5" or not w["text"].strip():
                continue
            key = (w["block_num"], w["par_num"], w["line_num"])
            top = int(w["top"])
            h = int(w["height"])
            lines.setdefault(key, []).append((top + h / 2, w["text"]))
        # Assign each line to a band by its words' median y-center.
        band_lines = {bi: [] for bi in range(len(bands))}
        for key, words in lines.items():
            ys = sorted(yc for yc, _ in words)
            yc = ys[len(ys) // 2]
            text = " ".join(t for _, t in words)
            for bi, (ys0, ys1) in enumerate(ranges):
                if ys0 - 2 <= yc <= ys1 + 2:
                    band_lines[bi].append(text)
                    break
        for bi in range(len(bands)):
            texts = band_lines[bi]
            joined = " / ".join(texts)
            nums = [n for n in (parse_number(t) for t in texts)
                    if n is not None]
            # A merged band may also show its second number mid-line.
            if len(nums) < 2 and texts:
                m2 = re.search(r"\b([0-9]{3,4})\s*\.\s*[A-ZÄÖÜ]{3,}",
                               joined[12:])
                if m2 and int(m2.group(1)) not in nums:
                    nums.append(int(m2.group(1)))
            if len(nums) == 1:
                status = "ok"
            elif len(nums) == 0:
                status = "none" if not joined.strip() else "unclear"
            else:
                status = "merged"
            rows_out.append([page, bi, match.get((page, bi), ""),
                             joined, ";".join(map(str, nums)), status])
        print(f"page {page:02d}: {len(bands)} bands", flush=True)

    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page", "band_index", "crop_file", "ocr_text",
                    "numbers", "status"])
        w.writerows(rows_out)
    print(f"wrote {OUT} ({len(rows_out)} bands)")


if __name__ == "__main__":
    main()
