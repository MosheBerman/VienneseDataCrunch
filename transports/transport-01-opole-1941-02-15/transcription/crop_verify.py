#!/usr/bin/env python3
"""Verify review crops match their rows: fresh full-strip OCR per crop.

OCR each crop jpg (Tesseract deu, psm 7), parse the printed lead
number, surname token and date, compare against the transcription
row. Streaming output, 2 workers, per-call timeout. Also flags
merged bands (two printed numbers in one strip).

Output: out/crop_verify.csv
"""
import csv
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REVIEW = HERE / "review"
CROPS = REVIEW / "crops"
TRANSCRIPTION = HERE.parent / "transport-01_transcription.csv"
OUT = HERE / "out" / "crop_verify.csv"

LEAD_TOK_RE = re.compile(r"^\s*\S{0,3}?([0-9lIOoSsBZG]{1,4})\s*[.,]")


def normalize_number(s):
    return (s.replace("l", "1").replace("I", "1").replace("O", "0")
             .replace("o", "0").replace("S", "5").replace("s", "5")
             .replace("B", "8").replace("Z", "2").replace("G", "6"))


def ocr(path):
    try:
        r = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", "deu", "--psm", "7"],
            capture_output=True, text=True, timeout=30)
        return " ".join(r.stdout.split())
    except subprocess.TimeoutExpired:
        return ""


def parse(text):
    m = LEAD_TOK_RE.match(text.strip())
    number = None
    if m:
        digits = normalize_number(m.group(1))
        if digits.isdigit():
            number = int(digits)
    dm = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    date = None
    if dm:
        date = f"{int(dm.group(1))}.{int(dm.group(2))}.{dm.group(3)}"
    rest = text[m.end():] if m else text
    toks = re.findall(r"[A-ZÄÖÜ]{2,}", rest)
    surname = toks[0] if toks else None
    # merged band? a second "NNN." pattern after the first 15 chars
    second = re.search(r"\b([0-9]{3,4})\s*\.\s*[A-ZÄÖÜ]{3,}",
                       text[15:])
    merged = second.group(1) if second else None
    return number, surname, date, merged


def lev(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > 3:
        return 99
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[lb]


def main():
    rows = {int(r["list_no"]): r
            for r in csv.DictReader(TRANSCRIPTION.open())}
    jobs = []
    for p in sorted(CROPS.glob("row-*.jpg"),
                    key=lambda p: int(p.stem.split("-")[1])):
        jobs.append((p, int(p.stem.split("-")[1])))
    for p in sorted(CROPS.glob("unassigned-*.jpg")):
        jobs.append((p, None))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    f = OUT.open("w", newline="")
    w = csv.writer(f)
    w.writerow(["crop", "list_no", "ocr_text", "ocr_number",
                "ocr_surname", "ocr_date", "merged_second",
                "row_surname_raw", "row_birth_date", "num_match",
                "surname_match", "date_match", "verdict"])
    done = 0
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(ocr, p): (p, n) for p, n in jobs}
        for fut in as_completed(futs):
            p, n = futs[fut]
            text = fut.result()
            number, surname, date, merged = parse(text)
            row = rows.get(n) if n is not None else None
            if row is None:
                w.writerow([p.name, "", text, number, surname, date,
                            merged, "", "", "", "", "", "unassigned"])
            else:
                raw = re.sub(r"[^A-ZÄÖÜ]", "",
                             row["surname_raw"].upper())
                sname = surname or ""
                sdist = lev(sname, raw) if sname else 99
                surname_match = ("exact" if sdist == 0 else
                                 "close" if sdist <= 2 else "NO")
                num_match = ("exact" if number == n else
                             "close" if number is not None and
                             len(str(number)) == len(str(n)) and
                             sum(a != b for a, b in
                                 zip(str(number), str(n))) == 1
                             else "NO")
                bd = row["birth_date"]
                if bd:
                    y, mth, d = bd.split("-")
                    want = f"{int(d)}.{int(mth)}.{y}"
                    date_match = ("exact" if date == want else
                                  "close" if date and
                                  sum(a != b for a, b in
                                      zip(date.replace(".", ""),
                                          want.replace(".", ""))) <= 1
                                  and len(date.replace(".", "")) ==
                                  len(want.replace(".", ""))
                                  else "NO")
                else:
                    want, date_match = "", "nodate"
                if num_match == "NO" or surname_match == "NO":
                    verdict = "FLAG"
                elif num_match == "close" or surname_match == "close" or \
                        date_match in ("NO", "close"):
                    verdict = "check"
                else:
                    verdict = "ok"
                if merged:
                    verdict = "MERGED:" + verdict
                w.writerow([p.name, n, text, number, surname, date,
                            merged, raw, want, num_match,
                            surname_match, date_match, verdict])
            done += 1
            if done % 100 == 0:
                f.flush()
                print(f"{done}/{len(jobs)}", flush=True)
    f.close()
    print(f"wrote {OUT} ({len(jobs)} crops)")


if __name__ == "__main__":
    main()
