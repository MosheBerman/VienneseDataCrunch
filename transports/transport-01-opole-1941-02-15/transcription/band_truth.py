#!/usr/bin/env python3
"""Establish the printed number of every band.

Combines the stack-OCR parses (band_numbers.csv, with the page-5 wide
re-cut) with per-page sequence repair: printed numbers run
consecutively down each page, so confident reads anchor their
neighbours. Anything not forced by the sequence is flagged for
visual decision, never guessed.

Output: out/band_truth.csv
  page, band_index, crop_file, numbers, source, flag
numbers: ';'-separated printed numbers in this band (2+ = merged band,
split at fix time). Empty = non-data band (header/signature/blank).
source: ocr | seq | visual-pending
flag: '' | NEEDS-VISUAL | MERGED | DUP | GAP
"""
import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "band_truth.csv"

JUNK = " |:;\"'°*«»#+=_~^`\\"
CONFUSE = str.maketrans({"l": "1", "I": "1", "O": "0", "o": "0",
                         "S": "5", "s": "5", "B": "8", "Z": "2",
                         "G": "6", "T": "7"})


def tolerant_parse(text):
    """First plausible printed number at the start of the strip text."""
    if not text:
        return None
    first = text.split(" / ")[0]
    s = first.lstrip(JUNK).lstrip()
    # Skip a stray leading token (annotation mark / single digit or
    # char) when the next token is a 2-4 digit number, e.g. "4 738.",
    # "3 709.", "B 753.". Genuine numbers are safe: "7. NAME" has no
    # second numeric token, and "41. NAME" fails the \s+ match.
    m0 = re.match(r"^(\S{1,2})\s+([0-9lIOoSsBZG]{2,4})\s*[.,:»%\"”’]",
                  s)
    if m0:
        s = s[len(m0.group(1)):].lstrip()
    m = re.match(r"([0-9lIOoSsBZG]{1,4})\s*[.,:»%\"”’]?", s)
    if not m:
        return None
    digits = m.group(1).translate(CONFUSE)
    if not digits.isdigit():
        return None
    return int(digits)


def looks_data(text, page=None, block=None):
    if not text.strip():
        return False
    low = text.lower()
    if "verzeichnis" in low or "geheime" in low or "staatspolizei" in low:
        return False
    if "b.-nr" in low or "übernomm" in low or "b.-nr" in text:
        return False
    if re.search(r"[A-ZÄÖÜ]{3,}", text):
        return True
    if re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", text):
        return True
    # A band that parses to a plausible printed number with real
    # content is a data band even when OCR mangled the caps/date
    # (e.g. "3 709. Begall ärnst ler, 30. 5.1926").
    p = tolerant_parse(text)
    if p is not None and len(text.strip()) > 12:
        if block is None or block[0] - 10 <= p <= block[1] + 10:
            return True
    return False


def main():
    rows = list(csv.DictReader(open(HERE / "out" / "band_numbers.csv")))
    p05 = {int(r["band_index"]): r
           for r in csv.DictReader(open(HERE / "out" / "band_numbers_p05.csv"))}
    psm7 = {(int(r["page"]), int(r["band_index"])): r["psm7_text"]
            for r in csv.DictReader(open(HERE / "out" / "band_psm7.csv"))}
    psm11 = {(int(r["page"]), int(r["band_index"])): r["psm11_text"]
             for r in csv.DictReader(open(HERE / "out" / "band_psm11.csv"))}
    # Hundred-block bounds per page (loose, used only to stop sequence
    # extension from numbering signature/footer bands, and to reject
    # implausible stack parses in favour of the psm7 fallback).
    BLOCK = {}
    for p in range(1, 7):
        BLOCK[p] = (1, 200)
    for p in range(7, 13):
        BLOCK[p] = (201, 401)
    for p in range(13, 16):
        BLOCK[p] = (402, 500)
    for p in range(16, 19):
        BLOCK[p] = (501, 600)
    for p in range(19, 22):
        BLOCK[p] = (601, 700)
    for p in range(22, 25):
        BLOCK[p] = (701, 800)
    for p in range(25, 28):
        BLOCK[p] = (801, 901)
    for p in range(28, 31):
        BLOCK[p] = (902, 1000)

    for r in rows:
        pg, band = int(r["page"]), int(r["band_index"])
        if pg == 5 and band in p05:
            r.update({k: p05[band][k]
                      for k in ("ocr_text", "numbers", "status")})
        # Enrich: fall back to psm7, then psm11, when the stack text
        # is empty, unparseable, or parses outside the page's block.
        stack_parse = tolerant_parse(r["ocr_text"])
        lo, hi = BLOCK[pg]
        if stack_parse is None or not (lo - 10 <= stack_parse <= hi + 10):
            for alt in (psm7.get((pg, band)), psm11.get((pg, band))):
                if alt and (tolerant_parse(alt) is not None
                            or not r["ocr_text"].strip()):
                    r["ocr_text"] = alt
                    break

    # Visual ground truth (crops/regions read by eye, 2026-11-13).
    # Forced numbers; [] = forced non-data (blank/signature band the
    # sequence extension wrongly numbered).
    OVERRIDES = {
        (12, 10): [399], (22, 37): [733], (22, 43): [738],
        (6, 15): [],
        (2, 37): [73],
        (3, 8): [83], (3, 9): [84], (3, 10): [85], (3, 28): [],
        (9, 20): [], (9, 24): [],
        (10, 0): [],
        (14, 9): [453], (14, 10): [454], (14, 11): [454],  # genuine duplicate in print
        (19, 10): [610, 611], (19, 11): [612],
        (20, 3): [],
        (22, 38): [734], (22, 39): [735], (22, 40): [736],
        (22, 41): [737],
        (23, 0): [], (23, 1): [],
        (23, 2): [739, 740], (23, 3): [741, 742, 743],
        (23, 26): [765], (23, 27): [766], (23, 28): [767],
        (23, 29): [768], (23, 31): [769],
        (23, 40): [777], (23, 41): [778], (23, 42): [779],
        (23, 43): [780], (23, 44): [781],
        (24, 0): [], (24, 1): [], (24, 2): [], (24, 3): [],
        (24, 4): [],
        (24, 7): [784, 785], (24, 8): [786, 787],
        (25, 3): [801], (25, 16): [812],
        (27, 15): [887, 888],
        (28, 33): [935], (28, 34): [936], (28, 35): [937], (28, 36): [938],
    }

    by_page = {}
    for r in rows:
        by_page.setdefault(int(r["page"]), []).append(r)

    truth = []
    for page in sorted(by_page):
        bands = sorted(by_page[page], key=lambda r: int(r["band_index"]))
        n = len(bands)
        parsed = [tolerant_parse(r["ocr_text"]) for r in bands]
        data = [looks_data(r["ocr_text"], page, BLOCK[page])
                for r in bands]
        # Merged-band second numbers: any additional NNN. pattern.
        # 1-4 digits: two-digit list numbers (pp. 1-3) merge too.
        extra = []
        for r in bands:
            m2 = re.findall(r"\b([0-9]{1,4})\s*\.\s*[A-ZÄÖÜ]{3,}",
                            r["ocr_text"][12:])
            extra.append([int(x) for x in m2])

        # Confident anchors: 3-4 digit parse, data band, and the parse
        # is within 150 of the page's median confident parse (kills
        # wild reads like 9453/9082/41/18 on first pass; sequence
        # repair below re-admits them if they fit).
        cands = [p for p, d in zip(parsed, data)
                 if p is not None and d and 100 <= p <= 1000]
        med = sorted(cands)[len(cands) // 2] if cands else 0
        anchor = [False] * n
        for i, p in enumerate(parsed):
            if p is not None and data[i] and 1 <= p <= 1000 \
                    and abs(p - med) <= 120:
                anchor[i] = True
        # Prune anchors that break monotonicity with neighbours.
        changed = True
        while changed:
            changed = False
            seq = [(i, parsed[i]) for i in range(n) if anchor[i]]
            for (i, a), (j, b) in zip(seq, seq[1:]):
                if b <= a or b - a > (j - i) + 2:
                    # Drop the one further from the page median run.
                    anchor[j if abs(b - med) > abs(a - med) else i] = False
                    changed = True
                    break

        numbers = [[] for _ in range(n)]
        source = [""] * n
        flag = [""] * n
        # Visual overrides: forced anchors / forced non-data.
        for i in range(n):
            if (page, i) in OVERRIDES:
                ov = OVERRIDES[(page, i)]
                if ov:
                    anchor[i] = True
                    parsed[i] = ov[0]
                    numbers[i] = list(ov)
                    source[i] = "visual"
                else:
                    anchor[i] = False
                    data[i] = False
        for i in range(n):
            if anchor[i] and not numbers[i]:
                numbers[i] = [parsed[i]]
                source[i] = "ocr"
        # Fill between anchors.
        anchors = [i for i in range(n) if anchor[i]]
        # Extend with virtual anchors at the ends using sequence only
        # when the fill is forced (handled below per segment).
        segments = []
        if anchors:
            segments.append((None, anchors[0]))
            for a, b in zip(anchors, anchors[1:]):
                segments.append((a, b))
            segments.append((anchors[-1], None))
        for a, b in segments:
            lo = 0 if a is None else a + 1
            hi = n - 1 if b is None else b - 1
            idxs = [i for i in range(lo, hi + 1) if data[i]]
            if a is not None and b is not None:
                na = max(numbers[a]) if numbers[a] else parsed[a]
                nb = min(numbers[b]) if numbers[b] else parsed[b]
                need = nb - na - 1
                if need == len(idxs):
                    for k, i in enumerate(idxs):
                        numbers[i] = [na + 1 + k]
                        source[i] = "seq"
                elif need < len(idxs):
                    # More data bands than numbers: some band is a
                    # split fragment or a misread duplicate.
                    for i in idxs:
                        flag[i] = "NEEDS-VISUAL"
                else:
                    # Fewer bands than numbers: merged bands likely.
                    for i in idxs:
                        flag[i] = "NEEDS-VISUAL"
                    # Still fill greedily where extra[] supplies the
                    # missing numbers (merged bands).
                    expect = na + 1
                    for i in idxs:
                        nums = [expect]
                        if extra[i]:
                            for e in extra[i]:
                                if e == expect + 1:
                                    nums.append(e)
                                    expect += 1
                        numbers[i] = nums
                        source[i] = "seq"
                        expect += 1
                    if expect != nb:
                        for i in idxs:
                            flag[i] = "NEEDS-VISUAL"
            elif a is not None:
                # After last anchor: extend forward, capped at the
                # hundred-block max; anything beyond is flagged, not
                # numbered (signature/footer bands).
                na = max(numbers[a]) if numbers[a] else parsed[a]
                expect = na + 1
                for i in idxs:
                    if expect > BLOCK[page][1]:
                        flag[i] = "NEEDS-VISUAL"
                        continue
                    numbers[i] = [expect]
                    source[i] = "seq"
                    expect += 1
            elif b is not None:
                # Before first anchor: extend backward, capped at the
                # block start.
                nb = min(numbers[b]) if numbers[b] else parsed[b]
                expect = nb - 1
                for i in reversed(idxs):
                    if expect < BLOCK[page][0]:
                        flag[i] = "NEEDS-VISUAL"
                        continue
                    numbers[i] = [expect]
                    source[i] = "seq"
                    expect -= 1
        # Merged bands: attach extra numbers where the sequence needs
        # them (band already has 1 number and extra has the next one).
        for i in range(n):
            if extra[i] and numbers[i]:
                for e in extra[i]:
                    if e == numbers[i][-1] + 1 and e not in numbers[i]:
                        numbers[i].append(e)
                        flag[i] = "MERGED"
        # Non-data bands keep no numbers; data bands with none get flagged.
        for i in range(n):
            if not data[i]:
                numbers[i] = []
                if source[i]:
                    source[i] = ""
            elif not numbers[i]:
                flag[i] = "NEEDS-VISUAL"
        # Duplicate numbers on one page: flag all holders.
        seen = {}
        for i in range(n):
            for num in numbers[i]:
                seen.setdefault(num, []).append(i)
        for num, idxs in seen.items():
            if len(idxs) > 1:
                for i in idxs:
                    if flag[i] != "MERGED":
                        flag[i] = "DUP"
        for i, r in enumerate(bands):
            truth.append([page, r["band_index"], r["crop_file"],
                          ";".join(map(str, numbers[i])),
                          source[i] or ("ocr" if anchor[i] else ""),
                          flag[i]])

    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page", "band_index", "crop_file", "numbers",
                    "source", "flag"])
        w.writerows(truth)
    import collections
    print(collections.Counter(r[5] or "clean" for r in truth))
    print("flagged bands:")
    for r in truth:
        if r[5] in ("NEEDS-VISUAL", "DUP"):
            print(r)


if __name__ == "__main__":
    main()
