#!/usr/bin/env python3
"""Post-process the rowbox OCR rows for Transport 1.

- Splits name_raw into surname / given_names (handles "X false Y" double
  surnames, e.g. "BERMANN false LEHRHAUPT").
- Clusters surname variants within the transport (families travel in
  blocks, so a surname recurs within a few rows): union-find over rows
  whose surnames are within edit distance 2 and whose rows are within a
  window of 12 list numbers; canonical form = the cluster's most common
  reading, preferring forms without OCR-suspicious characters.
  Corrections are recorded in surname_fix, never overwritten silently.
- Validates list-number continuity across the whole transport and
  summarizes flags into a review list.

Input : out/rowbox_full/transport-01_rows.csv
Output: ../transport-01_transcription.csv  (the deliverable)
        out/rowbox_full/review.csv         (flagged rows for human check)
        prints a validation summary
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "out" / "rowbox_full" / "transport-01_rows.csv"
DST = HERE.parent / "transport-01_transcription.csv"
REVIEW = HERE / "out" / "rowbox_full" / "review.csv"

sys.path.insert(0, str(HERE))
from ocr_pilot import levenshtein  # noqa: E402

SUSPECT = re.compile(r"[^A-ZÄÖÜß \-]")


def split_name(name: str):
    toks = name.split()
    if len(toks) >= 3 and toks[1].lower() == "false":
        return " ".join(toks[:3]), " ".join(toks[3:])
    if not toks:
        return "", ""
    return toks[0], " ".join(toks[1:])


def main():
    rows = list(csv.DictReader(SRC.open()))
    for r in rows:
        r["list_no"] = int(r["list_no"])
        sur, giv = split_name(r["name_raw"])
        r["surname_raw"], r["given_names"] = sur, giv
        r["surname"] = sur
        r["surname_fix"] = ""

    # --- surname clustering ---------------------------------------------
    parent = list(range(len(rows)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Clustering v2 (scored, conservative). The v1 rules (edit distance
    # <= 2 + 12-row window, union-find chaining) merged unrelated names
    # through garbage tokens - scored afterwards, 108 of its 179 fixes
    # were low-confidence (KOHN->ARON, SINGER->BERGER). Now: only
    # letters-only forms >= 4 chars take part; two forms join only at
    # pair score >= 0.88 (Jaro-Winkler/Levenshtein blend from
    # cluster_scores); a fix is APPLIED only at score >= 0.90 with the
    # canonical attested in the Lehmann 1940/41 surname index or at
    # least twice as frequent; anything weaker becomes a
    # surname_suggestion flag, not a change.
    from cluster_scores import jaro_winkler
    from crossmatch import norm as xnorm
    import json as _json

    def pair_score(a, b):
        lev_sim = 1 - levenshtein(a, b) / max(len(a), len(b))
        return 0.65 * jaro_winkler(a, b) + 0.35 * lev_sim

    map_surnames = set()
    for dirname in ("data", "data39", "data40", "data41"):
        recdir = HERE.parents[2] / dirname / "records"
        for shard in recdir.glob("r*.json"):
            for rec in _json.loads(shard.read_text()).values():
                if rec.get("s"):
                    map_surnames.add(xnorm(rec["s"]))

    def clusterable(s):
        return len(s) >= 4 and re.fullmatch(r"[A-ZÄÖÜß]+", s or "") is not None

    def attested(s):
        return xnorm(s) in map_surnames

    by_sur = defaultdict(list)
    for i, r in enumerate(rows):
        by_sur[r["surname_raw"]].append(i)
    surs = [s for s in by_sur if clusterable(s)]
    for ai in range(len(surs)):
        for bi in range(ai + 1, len(surs)):
            a, b = surs[ai], surs[bi]
            if abs(len(a) - len(b)) > 2 or pair_score(a, b) < 0.88:
                continue
            near = any(
                abs(rows[i]["list_no"] - rows[j]["list_no"]) <= 12
                for i in by_sur[a] for j in by_sur[b]
            )
            if near:
                union(by_sur[a][0], by_sur[b][0])
    clusters = defaultdict(list)
    for i, r in enumerate(rows):
        if clusterable(r["surname_raw"]):
            clusters[find(i)].append(i)
    n_fixed = 0
    n_suggested = 0
    for members in clusters.values():
        forms = Counter(rows[i]["surname_raw"] for i in members)
        if len(forms) <= 1:
            continue
        canon = sorted(
            forms.items(),
            key=lambda kv: (not attested(kv[0]), -kv[1],
                            bool(SUSPECT.search(kv[0])), kv[0]),
        )[0][0]
        for i in members:
            raw = rows[i]["surname_raw"]
            if raw == canon:
                continue
            sc = pair_score(raw, canon)
            strong = sc >= 0.90 and (
                attested(canon) or forms[canon] >= 2 * forms[raw])
            if strong:
                rows[i]["surname"] = canon
                rows[i]["surname_fix"] = f"{raw}->{canon}"
                n_fixed += 1
            elif sc >= 0.82:
                rows[i]["flags"] = (
                    rows[i]["flags"] + f";surname_suggestion:{canon}"
                ).strip(";")
                n_suggested += 1

    # NOTE: no rows are dropped and no numbers are renumbered here.
    # Garbage bands (signature flourishes) and misaligned rows exist in
    # the output; they carry flags and their raw OCR line, so a human
    # reviewer can find and fix them. Dropping/renumbering heuristics
    # were tried and removed - each one silently ate real rows.

    # --- continuity validation ------------------------------------------
    nos = sorted(r["list_no"] for r in rows)
    dupes = [n for n, c in Counter(nos).items() if c > 1]
    missing = [n for n in range(nos[0], nos[-1] + 1) if n not in set(nos)]

    # --- write outputs ----------------------------------------------------
    with open(DST, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["list_no", "page", "surname", "given_names", "birth_date",
                    "surname_raw", "surname_fix", "flags", "ocr_line"])
        for r in sorted(rows, key=lambda r: r["list_no"]):
            w.writerow([r["list_no"], r["page"], r["surname"], r["given_names"],
                        r["birth_date"], r["surname_raw"], r["surname_fix"],
                        r["flags"], r["line"] if "line" in r else r["ocr_line"]])
    flagged = [r for r in rows if r["flags"] or r["surname_fix"]]
    with open(REVIEW, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["list_no", "page", "surname", "given_names", "birth_date",
                    "flags", "surname_fix"])
        for r in sorted(flagged, key=lambda r: r["list_no"]):
            w.writerow([r["list_no"], r["page"], r["surname"], r["given_names"],
                        r["birth_date"], r["flags"], r["surname_fix"]])

    print(f"rows: {len(rows)}  range: {nos[0]}-{nos[-1]}")
    print(f"duplicate list numbers: {dupes[:20]}{'...' if len(dupes) > 20 else ''}")
    print(f"missing list numbers: {missing[:40]}{'...' if len(missing) > 40 else ''}")
    print(f"surname fixes applied: {n_fixed}")
    print(f"surname suggestions (not applied): {n_suggested}")
    print(f"flagged rows for review: {len(flagged)}")
    print(f"rows missing a date: {sum(1 for r in rows if not r['birth_date'])}")


if __name__ == "__main__":
    main()
