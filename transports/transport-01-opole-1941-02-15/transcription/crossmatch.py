#!/usr/bin/env python3
"""Cross-match Transport 1 transcription rows against the Lehmann map's
1940 and 1941 person datasets (VienneseDataCrunch data40/data41 shards).

Normalization: uppercase, umlauts folded (Ä->A, Ö->O, Ü->U, ß->SS, plus
AE/OE/UE expansions tried as alternates), punctuation stripped. The
forced names Sara/Israel are dropped from given-name comparison.

Tiers:
  exact : surname and first given name equal (either year)
  near1 : surname edit distance <= 1 and given name equal
  near2 : surname equal and given edit distance <= 1,
          or surname distance <= 2 and given initials equal

Outputs out/crossmatch.csv (one line per transcription row with its
best tier and up to 3 candidate map records) and prints a summary,
including how many garbled surnames (no exact match) get a unique
near1 candidate whose spelling could correct them.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]  # VienneseDataCrunch/
sys.path.insert(0, str(HERE))
from ocr_pilot import levenshtein  # noqa: E402

TRANSCRIPTION = HERE.parent / "transport-01_transcription.csv"
OUT = HERE / "out" / "crossmatch.csv"


def norm(s: str) -> str:
    s = (s or "").upper()
    s = (s.replace("Ä", "A").replace("Ö", "O").replace("Ü", "U")
         .replace("ß", "SS"))
    s = re.sub(r"[^A-Z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def first_given(g: str) -> str:
    toks = [t for t in norm(g).split() if t not in ("SARA", "ISRAEL", "ISR")]
    return toks[0] if toks else ""


# Given-name variants seen between the lists and the directories
# (the 1938 book lists Josef Bermann as "Jossel", his Yiddish name).
GIVEN_VARIANTS = {
    "JOSEF": {"JOSSEL", "JOSSSEL", "JOSEPH"},
    "JOSSEL": {"JOSEF"},
    "ISAK": {"ISAAK"},
    "ISAAK": {"ISAK"},
    "LEIB": {"LEO", "LEIB"},
    "HERSCH": {"HERSCH", "HERMANN"},
}


def given_forms(g: str):
    return {g} | GIVEN_VARIANTS.get(g, set())


def load_year(year: int):
    idx = defaultdict(list)
    dirname = "data" if year == 1938 else f"data{year % 100:02d}"
    recdir = REPO / dirname / "records"
    n = 0
    for shard in sorted(recdir.glob("r*.json")):
        data = json.loads(shard.read_text())
        for rec in data.values():
            sur = norm(rec.get("s", ""))
            giv = first_given(rec.get("g", ""))
            if sur:
                idx[(sur, giv)].append(
                    {"surname": rec.get("s", ""), "given": rec.get("g", ""),
                     "street": rec.get("st", ""), "hn": rec.get("hn", ""),
                     "district": rec.get("d", ""), "year": year})
                n += 1
    print(f"{year}: indexed {n} records, {len(idx)} name keys")
    return idx


def deletions(word: str):
    return {word[:i] + word[i + 1:] for i in range(len(word))}


YEARS = (1938, 1939, 1940, 1941)


def main():
    indexes = {y: load_year(y) for y in YEARS}
    by_sur = defaultdict(set)
    for idx in indexes.values():
        for (sur, giv) in idx:
            by_sur[sur].add(giv)
    # deletion-neighbourhood index for edit-distance<=1 surname lookup
    del_index = defaultdict(set)
    for sur in by_sur:
        del_index[sur].add(sur)
        for d in deletions(sur):
            del_index[d].add(sur)
    by_first = defaultdict(list)
    for sur in by_sur:
        by_first[sur[:1]].append(sur)

    def near1_surnames(sur):
        cands = set()
        for key in {sur} | deletions(sur):
            cands |= del_index.get(key, set())
        return {c for c in cands if levenshtein(c, sur) <= 1}

    def near2_surnames(sur, giv):
        out = []
        for cand in by_first.get(sur[:1], []):
            if abs(len(cand) - len(sur)) <= 2 and \
                    levenshtein(cand, sur) <= 2 and \
                    any(g[:1] == giv[:1] for g in by_sur[cand]):
                out.append(cand)
                if len(out) >= 3:
                    break
        return out

    rows = list(csv.DictReader(TRANSCRIPTION.open()))
    out = []
    stats = defaultdict(int)
    corrections = []
    for r in rows:
        sur_raw = r["surname_raw"] or r["surname"]
        # for "X false Y" double surnames, try both parts
        surs = [norm(s) for s in re.split(r"\s+FALSE\s+", sur_raw.upper())]
        giv = first_given(r["given_names"])
        best = None
        cands = []
        gforms = given_forms(giv) if giv else {giv}
        for sur in surs:
            for year in (1941, 1940, 1939, 1938):
                idx = indexes[year]
                hit = next((g for g in gforms if (sur, g) in idx), None)
                if hit is not None:
                    best = "exact"
                    stats[f"exact_in_{year}"] += 1
                    cands = idx[(sur, hit)][:3]
                    break
            if best:
                break
        if not best and giv:
            for sur in surs:
                for cand_sur in near1_surnames(sur):
                    hit = next((g for g in gforms if g in by_sur[cand_sur]),
                               None)
                    if hit is not None:
                        for year in (1941, 1940, 1939, 1938):
                            idx = indexes[year]
                            if (cand_sur, hit) in idx:
                                best = "near1"
                                cands = idx[(cand_sur, hit)][:3]
                                break
                    if best:
                        break
                if best:
                    break
        if not best and giv:
            for sur in surs:
                for cand_sur in near2_surnames(sur, giv):
                    best = "near2"
                    cands = [{"surname": cand_sur, "given": g,
                              "street": "", "hn": "", "district": "",
                              "year": ""} for g in list(by_sur[cand_sur])[:2]]
                    break
                if best:
                    break
        tier = best or "none"
        stats[tier] += 1
        if tier == "near1" and cands:
            spellings = {c["surname"] for c in cands}
            if len(spellings) == 1:
                corrections.append((r["list_no"], sur_raw,
                                    next(iter(spellings))))
        out.append({
            "list_no": r["list_no"], "surname": r["surname"],
            "given_names": r["given_names"], "birth_date": r["birth_date"],
            "tier": tier,
            "matches": " | ".join(
                f"{c['surname']} {c['given']} — {c['street']} {c['hn']} "
                f"({c['district']}, {c['year']})".strip()
                for c in cands),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    total = len(rows)
    for t in ("exact", "near1", "near2", "none"):
        print(f"{t}: {stats[t]} ({stats[t] / total:.1%})")
    for y in YEARS:
        print(f"  exact matches sourced from {y}: {stats[f'exact_in_{y}']}")
    print(f"unique-spelling near1 surname corrections available: "
          f"{len(corrections)}")
    for c in corrections[:15]:
        print(f"  row {c[0]}: {c[1]} -> {c[2]}")


if __name__ == "__main__":
    main()
