#!/usr/bin/env python3
"""Re-cut page 5 bands with a wider left margin (numbers sit left of
the standard 0.16w table crop) and OCR the stack for printed numbers.

Outputs out/band_numbers_p05.csv in the same format as band_numbers.py
(page 5 rows only), plus wide crop slices in review/crops_wide/.
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

PAGE = 5
X0 = 240  # wide left edge (numbers start ~303 on this page)
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
    srcs = sorted(glob.glob(str(HERE.parent / f"page-{PAGE:02d}_*.jpg")))
    img = cv2.imread(srcs[0], cv2.IMREAD_GRAYSCALE)
    desk = deskew(img)
    h, w = desk.shape
    table = crop_table(desk)
    bands = find_lines(table)
    y_off = int(0.095 * h)
    x1 = int(0.90 * w)
    wide_dir = HERE / "review" / "crops_wide"
    wide_dir.mkdir(parents=True, exist_ok=True)

    match = {}
    for r in csv.DictReader(open(HERE / "out" / "crop_band_match.csv")):
        if int(r["page"]) == PAGE:
            match[int(r["band_index"])] = r["crop"]

    parts = []
    ranges = []
    y = 0
    for bi, (y0, y1) in enumerate(bands):
        sl = desk[max(0, y0 + y_off - 6): y1 + y_off + 6, X0:x1]
        cv2.imwrite(str(wide_dir / f"p{PAGE:02d}-{bi:02d}.jpg"), sl,
                    [cv2.IMWRITE_JPEG_QUALITY, 82])
        parts.append(sl)
        ranges.append((y, y + sl.shape[0]))
        y += sl.shape[0]
        parts.append(np.full((SEP, sl.shape[1]), 255, dtype=np.uint8))
        y += SEP
    stack = np.vstack(parts)
    tmp = "/tmp/stack-p05-wide.png"
    cv2.imwrite(tmp, stack)
    r = subprocess.run(
        ["tesseract", tmp, "stdout", "-l", "deu", "--psm", "6", "tsv"],
        capture_output=True, text=True, timeout=120)
    lines = {}
    tsv = csv.DictReader(r.stdout.splitlines(), delimiter="\t",
                         quoting=csv.QUOTE_NONE)
    for word in tsv:
        if word["level"] != "5" or not word["text"].strip():
            continue
        key = (word["block_num"], word["par_num"], word["line_num"])
        top = int(word["top"])
        hh = int(word["height"])
        lines.setdefault(key, []).append((top + hh / 2, word["text"]))
    band_lines = {bi: [] for bi in range(len(bands))}
    for key, words in lines.items():
        ys = sorted(yc for yc, _ in words)
        yc = ys[len(ys) // 2]
        text = " ".join(t for _, t in words)
        for bi, (ys0, ys1) in enumerate(ranges):
            if ys0 - 2 <= yc <= ys1 + 2:
                band_lines[bi].append(text)
                break
    out = HERE / "out" / "band_numbers_p05.csv"
    with out.open("w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["page", "band_index", "crop_file", "ocr_text",
                     "numbers", "status"])
        for bi in range(len(bands)):
            texts = band_lines[bi]
            joined = " / ".join(texts)
            nums = [n for n in (parse_number(t) for t in texts)
                    if n is not None]
            if len(nums) < 2 and texts:
                m2 = re.search(r"\b([0-9]{3,4})\s*\.\s*[A-ZÄÖÜ]{3,}",
                               joined[12:])
                if m2 and int(m2.group(1)) not in nums:
                    nums.append(int(m2.group(1)))
            status = ("ok" if len(nums) == 1 else
                      "none" if not joined.strip() else
                      "merged" if len(nums) > 1 else "unclear")
            wr.writerow([PAGE, bi, match.get(bi, ""), joined,
                         ";".join(map(str, nums)), status])
    print(f"wrote {out} ({len(bands)} bands); wide slices in {wide_dir}")


if __name__ == "__main__":
    main()
