#!/usr/bin/env python3
"""Put street-only records at their house when another year already placed that address.

Why: every year was geocoded on its own. A record like "Gentzgasse 72, XVIII"
in 1942 can stay a street-level (amber) pin even though the same address got an
exact registry match in 1938. This script pools every house-level match from
all five years (data, data39..data42) into one address table and reuses it.

Rules (deliberately conservative):
  * Sources: records with m != 'fuzzy_street', a house number, and no
    geo_rescue flag (rescued streets are inferred, so they are not reused).
    When one street shows several different house numbers on the same
    point, only the majority number is kept as a source; the others (e.g.
    dozens of Donaustraße numbers all marked 'exact' on one point) are
    copies of a street-centre coordinate and are dropped, so the error
    isn't spread and relabelled as house-level.
  * Area guard: the chosen point must lie where that year's own house-level
    pins mostly carry the record's district (votes from a ~1 km box around
    the point). This catches source records that were themselves matched to
    a same-named street in another part of the city.
  * Outlier guard: the chosen point must lie within NEIGHBOUR_KM of another
    known house on the same street (compatible district). A street with no
    other known house needs the point within NEAR_PIN_KM of the current pin.
  * Targets: records with m == 'fuzzy_street', a house number, no geo_rescue.
  * Key: (street, house number incl. letter). "154-158" keys as 154.
  * Coordinates for one key are clustered (within 60 m = same building).
  * Accept a cluster whose source district matches the record's district
    (XIII/XIV/XV count as compatible: the Oct 1938 Groß-Wien renumbering moved
    Penzing to XIV and Rudolfsheim/Fünfhaus to XV). If more than one cluster
    matches, skip. If none matches, accept only when there is exactly one
    cluster and it lies within 1.5 km of the record's current street pin
    (covers OCR-damaged district numerals like "IV" for "XIV").
  * Accepted records get the cluster's coordinate and m = 'xyear_house'.

Usage (from the repo root):
  python3 pipeline/regeocode_cross_year.py            # report only
  python3 pipeline/regeocode_cross_year.py --holdout  # accuracy test
  python3 pipeline/regeocode_cross_year.py --write    # rewrite records, points, meta

--write rewrites <year>/records/*.json, <year>/points.geojson and the "pins"
count in <year>/meta.json. Running it twice is a no-op: rewritten records are
no longer 'fuzzy_street', and the script never uses its own output as a source.
"""
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

YEARS = [('data', 1938), ('data39', 1939), ('data40', 1940), ('data41', 1941), ('data42', 1942)]
NEW_M = 'xyear_house'
CLUSTER_M = 60      # metres: coordinates closer than this are the same building
NEAR_PIN_KM = 1.5   # fallback when the district does not match
NEIGHBOUR_KM = 0.5  # chosen point must be this close to another known house on the street
CELL = 0.003        # degrees; district-vote grid cell (~330 m x 220 m), 3x3 cells are polled
MIN_VOTES = 10
COMPAT = {'XIII': {'XIII', 'XIV'}, 'XIV': {'XIII', 'XIV', 'XV'}, 'XV': {'XIV', 'XV'}}


def cst(s):
    s = (s or '').strip().lower().replace('ß', 'ss')
    return re.sub(r'[^a-zäöü0-9]', '', s)


def chn(h):
    m = re.match(r'\s*(\d+)\s*([a-zA-Z])?(?![a-zA-Z])', h or '')
    if not m:
        return None
    return m.group(1) + (m.group(2) or '').upper()


def km(la1, lo1, la2, lo2):
    return math.hypot((la1 - la2) * 111.2, (lo1 - lo2) * 111.2 * math.cos(math.radians(48.2)))


def dist_ok(rd, sd):
    rd = (rd or '').strip().upper()
    sd = (sd or '').strip().upper()
    return rd == sd or sd in COMPAT.get(rd, ())


def load_year(ydir):
    shards = {}
    for fn in sorted(os.listdir(os.path.join(ydir, 'records'))):
        with open(os.path.join(ydir, 'records', fn), encoding='utf-8') as f:
            shards[fn] = json.load(f)
    return shards


def is_source(r):
    # NEW_M records are this script's own output; never reuse them, so a
    # second run changes nothing.
    return (r.get('la') is not None and r.get('m') not in ('fuzzy_street', NEW_M)
            and not r.get('geo_rescue') and chn(r.get('hn')) and cst(r.get('st')))


def is_target(r):
    return (r.get('m') == 'fuzzy_street' and r.get('la') is not None
            and not r.get('geo_rescue') and chn(r.get('hn')) and cst(r.get('st')))


def suspect_points(year_shards):
    """(point, street) -> majority house number there, where one street shows
    several different house numbers on the same coordinate (to ~10 m).

    Different houses of one street cannot share a point, so this is the mark
    of a street-centre coordinate copied onto house-level records. Only the
    majority number (None if there is none) is trusted there. Built from the
    pipeline's own house-level records only, so it does not change when this
    script rewrites street-only records.
    """
    at = defaultdict(Counter)
    for shards in year_shards.values():
        for d in shards.values():
            for r in d.values():
                if is_source(r):
                    at[((round(r['la'], 4), round(r['lo'], 4)), cst(r['st']))][chn(r['hn'])] += 1
    dom = {}
    for k, c in at.items():
        if len(c) < 2:
            continue
        h, n = c.most_common(1)[0]
        dom[k] = h if n * 2 > sum(c.values()) else None
    return dom


def on_street_point(r, spts):
    """True when r is a house-level record that copies a street-centre point."""
    k = ((round(r['la'], 4), round(r['lo'], 4)), cst(r.get('st')))
    return k in spts and spts[k] != chn(r.get('hn'))


def build_table(year_shards, spts, skip_year=None):
    """key -> list of clusters {la, lo, n, districts:Counter, years:set}"""
    raw = defaultdict(Counter)
    for ydir, shards in year_shards.items():
        if ydir == skip_year:
            continue
        for d in shards.values():
            for r in d.values():
                if is_source(r) and not on_street_point(r, spts):
                    k = (cst(r['st']), chn(r['hn']))
                    raw[k][(r['la'], r['lo'], (r.get('d') or '').strip().upper(), ydir)] += 1
    table = {}
    for k, pts in raw.items():
        clusters = []
        # most-supported coordinates first, so each cluster centres on its best point
        for (la, lo, dd, yd), n in sorted(pts.items(), key=lambda kv: -kv[1]):
            for c in clusters:
                if km(la, lo, c['la'], c['lo']) * 1000 <= CLUSTER_M:
                    c['n'] += n
                    c['districts'][dd] += n
                    c['years'].add(yd)
                    break
            else:
                clusters.append({'la': la, 'lo': lo, 'n': n, 'districts': Counter({dd: n}), 'years': {yd}})
        table[k] = clusters
    by_street = defaultdict(list)
    for (s, h), clusters in table.items():
        for c in clusters:
            by_street[s].append((h, c))
    table['__street__'] = by_street
    return table


def has_neighbour(r, clu, table):
    """Is clu within NEIGHBOUR_KM of another known house on r's street (same district group)?
    Returns None when the street has no other known house."""
    s, h = cst(r['st']), chn(r['hn'])
    others = [c for hh, c in table['__street__'].get(s, ())
              if hh != h and any(dist_ok(r.get('d'), sd) for sd in c['districts'])]
    if not others:
        return None
    return min(km(clu['la'], clu['lo'], c['la'], c['lo']) for c in others) <= NEIGHBOUR_KM


def district_grid(shards, spts):
    """cell -> Counter(district) from a year's trusted house-level pins."""
    grid = defaultdict(Counter)
    for d in shards.values():
        for r in d.values():
            if is_source(r) and not on_street_point(r, spts):
                grid[(int(r['la'] // CELL), int(r['lo'] // CELL))][(r.get('d') or '').strip().upper()] += 1
    return grid


def area_ok(r, clu, grid):
    """True/False when the area around clu votes for/against r's district, None when too few votes."""
    ci, cj = int(clu['la'] // CELL), int(clu['lo'] // CELL)
    votes = Counter()
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            votes.update(grid.get((ci + di, cj + dj), {}))
    total = sum(votes.values())
    if total < MIN_VOTES:
        return None
    good = sum(n for dd, n in votes.items() if dist_ok(r.get('d'), dd))
    return good * 2 > total


def resolve(r, table, grid=None):
    """Return (cluster, reason) or (None, reason)."""
    clusters = table.get((cst(r['st']), chn(r['hn'])))
    if not clusters:
        return None, 'no-source'
    same = [c for c in clusters if any(dist_ok(r.get('d'), sd) for sd in c['districts'])]
    if len(same) > 1:
        return None, 'ambiguous'
    if len(same) == 1:
        clu, reason = same[0], 'district'
    elif len(clusters) == 1 and km(r['la'], r['lo'], clusters[0]['la'], clusters[0]['lo']) <= NEAR_PIN_KM:
        clu, reason = clusters[0], 'near-pin'
    else:
        return None, 'other-district'
    if grid is not None:
        ao = area_ok(r, clu, grid)
        if ao is False or (ao is None and km(r['la'], r['lo'], clu['la'], clu['lo']) > NEAR_PIN_KM):
            return None, 'wrong-area'
    nb = has_neighbour(r, clu, table)
    if nb is False:
        return None, 'outlier'
    if nb is None and km(r['la'], r['lo'], clu['la'], clu['lo']) > NEAR_PIN_KM:
        return None, 'outlier'
    return clu, reason


def qcode(m):
    return 0 if m == 'exact' else (2 if (m or '').startswith('fuzzy_street') else 1)


def build_points(shards, with_ir):
    recs = {}
    for d in shards.values():
        for k, r in d.items():
            recs[int(k)] = r
    groups = {}
    for i in sorted(recs):
        r = recs[i]
        if r.get('la') is None:
            continue
        key = (r.get('st'), r.get('hn'), r['lo'], r['la'])
        g = groups.get(key)
        if g is None:
            g = groups[key] = [[], [0, 0, 0], False]
        g[0].append(i)
        g[1][qcode(r.get('m'))] += 1
        if r.get('geo_rescue'):
            g[2] = True
    feats = []
    for (st, hn, lo, la), (ids, qc, ir) in groups.items():
        best = 0 if qc[0] else (1 if qc[1] else 2)
        props = {'m': ids, 'q': best, 'qc': qc}
        if with_ir and ir:
            props['ir'] = 1
        feats.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lo, la]},
                      'properties': props})
    return {'type': 'FeatureCollection', 'features': feats}


def dump(obj):
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)


def tally(shards):
    c = Counter()
    for d in shards.values():
        for r in d.values():
            c['total'] += 1
            m = r.get('m')
            c['street' if m == 'fuzzy_street' else 'house'] += 1
    return c


def holdout(year_shards, spts):
    print('Holdout test: each year\'s house-level matches are re-placed using only the other four years.')
    for ydir, label in YEARS:
        table = build_table(year_shards, spts, skip_year=ydir)
        grid = district_grid(year_shards[ydir], spts)
        c = Counter()
        errs = []
        for d in year_shards[ydir].values():
            for r in d.values():
                if not is_source(r) or r.get('m') != 'exact' or on_street_point(r, spts):
                    continue
                clu, why = resolve(r, table, grid)
                if clu is None:
                    c['skipped:' + why] += 1
                    continue
                e = km(r['la'], r['lo'], clu['la'], clu['lo']) * 1000
                errs.append(e)
                c['placed'] += 1
                c['<=25m' if e <= 25 else ('<=100m' if e <= 100 else '>100m')] += 1
        errs.sort()
        n = len(errs)
        print(f'  {label}: placed {c["placed"]}, within 25 m {c["<=25m"]/n*100:.2f}%, '
              f'26-100 m {c["<=100m"]/n*100:.2f}%, over 100 m {c[">100m"]/n*100:.2f}% '
              f'(median {errs[n // 2]:.1f} m)')


def main():
    write = '--write' in sys.argv
    year_shards = {ydir: load_year(ydir) for ydir, _ in YEARS}
    spts = suspect_points(year_shards)
    if '--holdout' in sys.argv:
        holdout(year_shards, spts)
        return
    table = build_table(year_shards, spts)
    print(f'address table: {len(table)} street+number keys')
    for ydir, label in YEARS:
        shards = year_shards[ydir]
        grid = district_grid(shards, spts)
        before = tally(shards)
        why = Counter()
        moved = []
        for fn, d in shards.items():
            for k, r in d.items():
                if not is_target(r):
                    continue
                clu, reason = resolve(r, table, grid)
                why[reason] += 1
                if clu is None:
                    continue
                moved.append(km(r['la'], r['lo'], clu['la'], clu['lo']))
                r['la'], r['lo'], r['m'] = clu['la'], clu['lo'], NEW_M
        after = tally(shards)
        t = before['total']
        print(f'{label}: street-only {before["street"]} ({before["street"]/t*100:.1f}%) -> '
              f'{after["street"]} ({after["street"]/t*100:.1f}%); placed at house {why["district"] + why["near-pin"]} '
              f'(district match {why["district"]}, single nearby candidate {why["near-pin"]}); '
              f'skipped: ambiguous {why["ambiguous"]}, other district {why["other-district"]}, wrong area {why["wrong-area"]}, outlier {why["outlier"]}, no source {why["no-source"]}')
        if moved:
            moved.sort()
            print(f'   pin moved: median {moved[len(moved)//2]*1000:.0f} m, 90th pct {moved[int(len(moved)*.9)]*1000:.0f} m')
        if write:
            for fn, d in shards.items():
                with open(os.path.join(ydir, 'records', fn), 'w', encoding='utf-8') as f:
                    f.write(json.dumps(d, ensure_ascii=False))
            pts_path = os.path.join(ydir, 'points.geojson')
            with open(pts_path, encoding='utf-8') as f:
                with_ir = '"ir":' in f.read()
            pts = build_points(shards, with_ir)
            with open(pts_path, 'w', encoding='utf-8') as f:
                f.write(dump(pts))
            meta_path = os.path.join(ydir, 'meta.json')
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)
            meta['pins'] = len(pts['features'])
            with open(meta_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(meta, ensure_ascii=False))
            print(f'   wrote {ydir}: {meta["pins"]} pins')


if __name__ == '__main__':
    main()
