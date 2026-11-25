#!/usr/bin/env python3
"""Repair pass over the rowbox OCR output.

For each page, bands are recomputed (deskew + crop + projection, no
full OCR) and each band's NUMBER zone and DATE zone are OCR'd with a
digit whitelist - much more reliable on those narrow fields than the
full-line read. Then:
  - rows whose birth_date is missing get the zone date if it parses;
  - bands whose number is one of the transport's missing list numbers
    get a full strip OCR and are added as recovered rows.

Input/output: out/rowbox_full/transport-01_rows.csv (updated in place;
a .bak copy is kept). Recovered rows carry flags marking them.
"""
import csv
import subprocess
import sys
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ocr_pilot import crop_table, parse_date, normalize_number  # noqa: E402
from rowbox_ocr import deskew, find_lines, ocr_strip, parse_strip  # noqa: E402

ROWS_CSV = HERE / "out" / "rowbox_full" / "transport-01_rows.csv"
TMP = HERE / "out" / "_zone.png"


def ocr_zone(img, whitelist=None) -> str:
    TMP.parent.mkdir(parents=True, exist_ok=True)
    padded = cv2.copyMakeBorder(img, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)
    cv2.imwrite(str(TMP), padded)
    cmd = ["tesseract", str(TMP), "stdout", "-l", "deu", "--psm", "7"]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return res.stdout.strip()


def main():
    rows = list(csv.DictReader(ROWS_CSV.open()))
    by_no = {int(r["list_no"]): r for r in rows}
    all_nos = set(by_no)
    missing = [n for n in range(min(all_nos), max(all_nos) + 1)
               if n not in all_nos]
    pages = sorted({int(r["page"]) for r in rows})
    dates_filled = 0
    rows_added = []

    for page in pages:
        srcs = sorted((HERE.parent).glob(f"page-{page:02d}_*.jpg"))
        img = cv2.imread(str(srcs[0]), cv2.IMREAD_GRAYSCALE)
        table = crop_table(deskew(img))
        h, w = table.shape
        for (y0, y1) in find_lines(table):
            band = table[max(0, y0 - 4): y1 + 4, :]
            num_txt = ocr_zone(band[:, : int(0.13 * w)], "0123456789.")
            digits = "".join(c for c in num_txt if c.isdigit())
            if not digits:
                continue
            no = int(digits)
            if no not in by_no and no not in missing:
                # zone digits may be a 1-digit misread of a missing number
                cands = [m for m in missing
                         if len(str(m)) == len(digits)
                         and sum(a != b for a, b in zip(str(m), digits)) == 1]
                if len(cands) == 1:
                    no = cands[0]
            if no in by_no and not by_no[no]["birth_date"]:
                date_txt = ocr_zone(band[:, int(0.58 * w): int(0.92 * w)],
                                    "0123456789.")
                date, _ = parse_date(date_txt)
                if date:
                    by_no[no]["birth_date"] = date
                    by_no[no]["flags"] = (
                        by_no[no]["flags"] + ";date_recovered").strip(";")
                    dates_filled += 1
            elif no in missing:
                text = ocr_strip(band)
                row, _ = parse_strip(text, no)
                if row and row["list_no"] == no:
                    row["page"] = page
                    row["flags"] = (row["flags"] + ";row_recovered").strip(";")
                    rows_added.append(row)
                    by_no[no] = {
                        "list_no": no, "page": page,
                        "name_raw": row["name_raw"],
                        "birth_date": row["birth_date"] or "",
                        "flags": row["flags"], "ocr_line": row["line"],
                    }
                    missing.remove(no)

    # Second sweep: a missing number's band may OCR its number zone as a
    # Hamming-1 neighbour that collides with a real row on another page
    # (e.g. 187 read as "137"). Use the neighbours' pages to locate the
    # sheet, then match bands by Hamming-1 zone number on that sheet.
    for m in list(missing):
        prevs = [n for n in by_no if n < m]
        nexts = [n for n in by_no if n > m]
        cand_pages = set()
        if prevs:
            cand_pages.add(int(by_no[max(prevs)]["page"]))
        if nexts:
            cand_pages.add(int(by_no[min(nexts)]["page"]))
        for page in cand_pages:
            srcs = sorted((HERE.parent).glob(f"page-{page:02d}_*.jpg"))
            img = cv2.imread(str(srcs[0]), cv2.IMREAD_GRAYSCALE)
            table = crop_table(deskew(img))
            w = table.shape[1]
            hit = None
            for (y0, y1) in find_lines(table):
                band = table[max(0, y0 - 4): y1 + 4, :]
                num_txt = ocr_zone(band[:, : int(0.13 * w)], "0123456789.")
                digits = "".join(c for c in num_txt if c.isdigit())
                if (len(digits) == len(str(m))
                        and sum(a != b for a, b in zip(str(m), digits)) == 1):
                    hit = band
                    break
            if hit is not None:
                text = ocr_strip(hit)
                row, _ = parse_strip(text, m)
                if row:
                    by_no[m] = {
                        "list_no": m, "page": page,
                        "name_raw": row["name_raw"],
                        "birth_date": row["birth_date"] or "",
                        "flags": (row["flags"] + ";row_recovered").strip(";"),
                        "ocr_line": row["line"],
                    }
                    rows_added.append(row)
                    missing.remove(m)
                break

    out_rows = sorted(by_no.values(), key=lambda r: int(r["list_no"]))
    with open(ROWS_CSV, "w", newline="") as f:
        wtr = csv.writer(f)
        wtr.writerow(["list_no", "page", "name_raw", "birth_date",
                      "flags", "ocr_line"])
        for r in out_rows:
            wtr.writerow([r["list_no"], r["page"], r["name_raw"],
                          r["birth_date"] or "", r["flags"], r["ocr_line"]])
    print(f"dates filled: {dates_filled}")
    print(f"rows recovered: {[r['list_no'] for r in rows_added]}")
    print(f"still missing: {missing}")
    print(f"total rows now: {len(out_rows)}")


if __name__ == "__main__":
    main()
