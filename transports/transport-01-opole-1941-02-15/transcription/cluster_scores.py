#!/usr/bin/env python3
"""Score the surname-cluster fixes probabilistically.

The delivered postprocess used hard rules (edit distance <= 2 within a
12-row window, canonical = most common form). This analysis re-scores
every applied fix with a similarity + frequency model and tiers it:

  score = 0.65 * jaro_winkler(a, b) + 0.35 * (1 - lev/maxlen)
  prior = canonical_count / (canonical_count + variant_count)

  high   : score >= 0.90 and prior >= 0.5   (fix almost surely right)
  medium : score >= 0.82 and prior >= 0.34
  low    : everything else                  (should be a suggestion,
                                             not an auto-fix)

Output: out/cluster_scores.csv with one line per applied fix.
"""
import csv
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ocr_pilot import levenshtein  # noqa: E402

TRANSCRIPTION = HERE.parent / "transport-01_transcription.csv"
OUT = HERE / "out" / "cluster_scores.csv"


def jaro(a: str, b: str) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    dist = max(la, lb) // 2 - 1
    am = [False] * la
    bm = [False] * lb
    matches = 0
    for i, ca in enumerate(a):
        lo = max(0, i - dist)
        hi = min(lb, i + dist + 1)
        for j in range(lo, hi):
            if not bm[j] and b[j] == ca:
                am[i] = bm[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    trans = 0
    k = 0
    for i in range(la):
        if am[i]:
            while not bm[k]:
                k += 1
            if a[i] != b[k]:
                trans += 1
            k += 1
    return (matches / la + matches / lb + (matches - trans / 2) / matches) / 3


def jaro_winkler(a: str, b: str) -> float:
    j = jaro(a, b)
    prefix = 0
    for x, y in zip(a, b):
        if x == y and prefix < 4:
            prefix += 1
        else:
            break
    return j + prefix * 0.1 * (1 - j)


def main():
    rows = list(csv.DictReader(TRANSCRIPTION.open()))
    counts = Counter(r["surname_raw"] for r in rows if r["surname_raw"])
    fixes = sorted({(r["surname_raw"], r["surname"])
                    for r in rows if r["surname_fix"]})
    out = []
    tiers = Counter()
    for raw, canon in fixes:
        lev_sim = 1 - levenshtein(raw, canon) / max(len(raw), len(canon))
        score = 0.65 * jaro_winkler(raw, canon) + 0.35 * lev_sim
        prior = counts[canon] / (counts[canon] + counts[raw])
        if score >= 0.90 and prior >= 0.5:
            tier = "high"
        elif score >= 0.82 and prior >= 0.34:
            tier = "medium"
        else:
            tier = "low"
        tiers[tier] += 1
        n_rows = sum(1 for r in rows if r["surname_fix"] and
                     r["surname_raw"] == raw and r["surname"] == canon)
        out.append({"variant": raw, "canonical": canon, "rows": n_rows,
                    "variant_count": counts[raw], "canonical_count": counts[canon],
                    "score": f"{score:.3f}", "prior": f"{prior:.2f}",
                    "tier": tier})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(sorted(out, key=lambda r: (r["tier"], -int(r["rows"]))))
    total_rows = sum(int(o["rows"]) for o in out)
    print(f"distinct fixes: {len(out)} covering {total_rows} rows")
    for t in ("high", "medium", "low"):
        n = sum(int(o["rows"]) for o in out if o["tier"] == t)
        print(f"  {t}: {tiers[t]} fixes, {n} rows")
    print("low-confidence fixes (should be suggestions, not auto-fixes):")
    for o in out:
        if o["tier"] == "low":
            print(f"  {o['variant']} -> {o['canonical']} "
                  f"(rows {o['rows']}, score {o['score']}, prior {o['prior']})")


if __name__ == "__main__":
    main()
