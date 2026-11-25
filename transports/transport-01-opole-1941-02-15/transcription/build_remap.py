#!/usr/bin/env python3
"""Build the corrected crop set: row N shows the strip that prints N.

Sources: out/band_truth.csv (band -> printed numbers, visually
verified 2026-11-13), the existing crop files (pixel-exact band
slices), and the wide page-5 re-cut slices (numbers visible).

Merged bands (2-3 printed rows in one slice) are split at the ink
valley between the text lines. Non-split bands are copied byte for
byte (no re-encode). Page 5 rows come from the wide slices.

Special case: printed 454 appears on TWO bands (typist repeated the
number, skipping 455). Row 454 (BAUER Rudolf) takes the first band,
row 455 (BAUER Risa) the second, asserted by surname.

Rows with no band (491 and 1001-1003: no such printed number) get no
crop. Writes into review/crops_fixed/ and a diff report at
out/remap_report.csv. The live review/crops/ directory is NOT
touched; promotion is a separate explicit step.
"""
import csv
import shutil
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
CROPS = HERE / "review" / "crops"
WIDE = HERE / "review" / "crops_wide"
FIXED = HERE / "review" / "crops_fixed"
TRUTH = HERE / "out" / "band_truth.csv"
CSV = HERE.parent / "transport-01_transcription.csv"


def split_points(gray, k):
    """Cut rows splitting a k-line strip into k single lines.

    Core-anchored: line cores are runs above 40% of the profile
    peak (gaps < 10px merged); the k heaviest cores are the lines,
    and cuts sit at the lowest-ink row of each inter-core gap.
    Falls back to deepest-valley splitting inside the heaviest
    core when fewer than k cores are found (touching lines).
    """
    h, w = gray.shape
    zone = gray[:, int(w * 0.05):int(w * 0.95)]
    prof = (zone < 128).sum(axis=1).astype(float)
    prof = np.convolve(prof, np.ones(3) / 3, mode="same")
    peak = prof.max()

    def cores(thresh_frac):
        above = prof >= thresh_frac * peak
        runs = []
        start = None
        for y in range(h):
            if above[y] and start is None:
                start = y
            elif not above[y] and start is not None:
                runs.append([start, y - 1])
                start = None
        if start is not None:
            runs.append([start, h - 1])
        merged = []
        for r in runs:
            if merged and r[0] - merged[-1][1] < 10:
                merged[-1][1] = r[1]
            else:
                merged.append(list(r))
        return merged

    found = cores(0.40)
    if len(found) < k:
        found = cores(0.25)
    if len(found) >= k:
        scored = sorted(
            ((prof[a:b + 1].sum(), a, b) for a, b in found),
            reverse=True)[:k]
        lines = sorted((a, b) for _, a, b in scored)
        cuts = []
        for i in range(k - 1):
            gap_a, gap_b = lines[i][1], lines[i + 1][0]
            cut = gap_a + int(np.argmin(prof[gap_a:gap_b + 1]))
            cuts.append(cut)
        return cuts
    # Fallback: deepest-valley splitting inside the ink span.
    ink = np.where(prof >= 0.10 * peak)[0]
    parts = [(int(ink[0]), int(ink[-1]) + 1)]
    while len(parts) < k:
        bi = max(range(len(parts)),
                 key=lambda i: prof[parts[i][0]:parts[i][1]].sum())
        a, b = parts[bi]
        lo = a + int((b - a) * 0.15)
        hi = a + int((b - a) * 0.85)
        cut = lo + int(np.argmin(prof[lo:hi]))
        parts = parts[:bi] + [(a, cut), (cut, b)] + parts[bi + 1:]
    cuts = sorted(p[1] for p in parts[:-1])
    bounds = [0] + cuts + [h]
    for i in range(k):
        if prof[bounds[i]:bounds[i + 1]].max() < 0.40 * peak:
            raise ValueError(f"part {i} has no line core")
    return cuts


def main():
    truth = list(csv.DictReader(open(TRUTH)))
    rows = {int(r["list_no"]): r
            for r in csv.DictReader(open(CSV))}
    FIXED.mkdir(exist_ok=True)

    # Band -> numbers.
    band_nums = {}
    for r in truth:
        nums = [int(x) for x in r["numbers"].split(";") if x]
        if nums:
            band_nums[(int(r["page"]), int(r["band_index"]))] = (
                r["crop_file"], nums)

    # Row -> (page, band, sub_index) assignment.
    assign = {}
    by_number = {}
    for (pg, band), (_, nums) in sorted(band_nums.items()):
        for sub, num in enumerate(nums):
            by_number.setdefault(num, []).append((pg, band, sub))
    for num, cands in by_number.items():
        if num == 454:
            assert len(cands) == 2, cands
            # Order check by surname: Rudolf first, Risa second.
            assert "BAUER Rudolf" in rows[454]["ocr_line"], rows[454]
            assert "BAUER Risa" in rows[455]["ocr_line"], rows[455]
            assign[454] = cands[0]
            assign[455] = cands[1]
        else:
            assert len(cands) == 1, (num, cands)
            assign[num] = cands[0]

    report = []
    splits_log = []
    for list_no in sorted(rows):
        old_file = CROPS / f"row-{list_no}.jpg"
        old_exists = old_file.exists()
        if list_no not in assign:
            report.append([list_no, "no-band", "", old_exists])
            continue
        pg, band, sub = assign[list_no]
        crop_file, nums = band_nums[(pg, band)]
        if pg == 5:
            src = WIDE / f"p05-{band:02d}.jpg"
        else:
            src = CROPS / crop_file
        dst = FIXED / f"row-{list_no}.jpg"
        if len(nums) == 1:
            shutil.copyfile(src, dst)
            how = "copy-wide" if pg == 5 else "copy"
        else:
            img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
            cuts = split_points(img, len(nums))
            bounds = [0] + cuts + [img.shape[0]]
            part = img[bounds[sub]:bounds[sub + 1], :]
            cv2.imwrite(str(dst), part,
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
            how = f"split-{len(nums)}:{sub}"
            splits_log.append((pg, band, nums, cuts, src.name))
        # Did the row's image change? Old file's band vs new band.
        old_band = None
        for r in truth:
            if r["crop_file"] == f"row-{list_no}.jpg":
                old_band = (r["page"], r["band_index"])
        changed = (old_band != (str(pg), str(band))) or not old_exists
        report.append([list_no, how, f"p{pg}b{band}",
                       old_exists, "CHANGED" if changed else "same"])

    with open(HERE / "out" / "remap_report.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["list_no", "how", "band", "old_existed", "status"])
        w.writerows(report)
    print("rows assigned:", len(assign))
    print("splits:", len(splits_log))
    for s in splits_log:
        print("split p%02d b%s %s cuts=%s from %s" % s)
    import collections
    print(collections.Counter(r[4] for r in report if len(r) > 4))
    print("no-band rows:", [r[0] for r in report if r[1] == "no-band"])


if __name__ == "__main__":
    main()
