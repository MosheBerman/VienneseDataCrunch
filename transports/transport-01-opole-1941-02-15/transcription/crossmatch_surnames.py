#!/usr/bin/env python3
"""Surname-only match pass against the 1938-1941 Lehmann directories.

Given names caused most misses in the person-level pass (Yiddish
variants, initials, spouses under other entries), so this pass asks
only: does this surname exist in the directories, and if not, what
close surnames do? Output feeds the manual review page.

Tiers per row:
  exact : a surname part (splitting "X false Y") is attested verbatim
  near1 : not exact, but surname(s) at edit distance <= 1 exist
  near2 : only distance-2 surnames exist
  none  : nothing within distance 2

Output: out/crossmatch_surnames.csv with, per row, the tier, per-year
entry counts for the exact surname, and candidate spellings with their
total entry counts across 1938-1941.
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
from crossmatch import norm, deletions  # noqa: E402
from ocr_pilot import levenshtein  # noqa: E402

TRANSCRIPTION = HERE.parent / "transport-01_transcription.csv"
OUT = HERE / "out" / "crossmatch_surnames.csv"
YEARS = ((1938, "data"), (1939, "data39"), (1940, "data40"),
         (1941, "data41"))


def main():
    counts = defaultdict(Counter)  # surname -> Counter(year -> entries)
    for year, dirname in YEARS:
        n = 0
        for shard in sorted((REPO / dirname / "records").glob("r*.json")):
            for rec in json.loads(shard.read_text()).values():
                s = norm(rec.get("s", ""))
                if s:
                    counts[s][year] += 1
                    n += 1
        print(f"{year}: {n} records")
    surnames = set(counts)
    del_index = defaultdict(set)
    for s in surnames:
        del_index[s].add(s)
        for d in deletions(s):
            del_index[d].add(s)

    def near(sur, maxd):
        cands = set()
        for key in {sur} | deletions(sur):
            cands |= del_index.get(key, set())
        if maxd == 1:
            return {c for c in cands if levenshtein(c, sur) <= 1}
        out = {c for c in cands if levenshtein(c, sur) <= 2}
        for c in list(cands):
            for key in deletions(c):
                for c2 in del_index.get(key, set()):
                    if levenshtein(c2, sur) <= 2:
                        out.add(c2)
        return out

    rows = list(csv.DictReader(TRANSCRIPTION.open()))
    out = []
    stats = Counter()
    for r in rows:
        raw = r["surname_raw"] or r["surname"]
        parts = [norm(p) for p in
                 re.split(r"\s+FALSE\s+", raw.upper()) if norm(p)]
        tier = "none"
        exact_years = ""
        cand_txt = ""
        hit = next((p for p in parts if p in surnames), None)
        if hit:
            tier = "exact"
            exact_years = " ".join(
                f"{y}:{counts[hit][y]}" for y, _ in YEARS if counts[hit][y])
            cand_txt = hit
        else:
            c1 = set()
            for p in parts:
                if len(p) >= 4:
                    c1 |= near(p, 1)
            c1.discard("")
            if c1:
                tier = "near1"
                cand_txt = " | ".join(
                    f"{c} ({sum(counts[c].values())})"
                    for c in sorted(c1, key=lambda c: -sum(counts[c].values()))[:4])
            else:
                c2 = set()
                for p in parts:
                    if len(p) >= 5:
                        c2 |= near(p, 2)
                if c2:
                    tier = "near2"
                    cand_txt = " | ".join(
                        f"{c} ({sum(counts[c].values())})"
                        for c in sorted(c2, key=lambda c: -sum(counts[c].values()))[:4])
        stats[tier] += 1
        out.append({"list_no": r["list_no"], "surname_raw": raw,
                    "surname": r["surname"], "tier": tier,
                    "exact_years": exact_years, "candidates": cand_txt})
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    total = len(rows)
    for t in ("exact", "near1", "near2", "none"):
        print(f"{t}: {stats[t]} ({stats[t] / total:.1%})")


if __name__ == "__main__":
    main()
