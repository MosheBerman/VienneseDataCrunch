#!/usr/bin/env python3
"""Build the IV. Teil (Haeuserverzeichnis / 1938 Houses) layer for the Lehmann map.

Reads ~/workspace/lehmann-map/parsed_ivteil_geocoded.jsonl and writes to
~/workspace/lehmann-map/web/site/data38h/ :
  points.geojson (one pin per address, resident member ids)
  records/rNNNN.json (1000 per shard, person-centric records)
  search.idx.json (token -> record ids)
  meta.json

Record format matches the existing 1942 layer (data42/) for UI compatibility:
  {s: surname, g: given, o: occupation, st: street, hn: house number,
   d: district, m: match quality, la/lo: lat/lon, pg: page id}

Quality mapping: geo_precision 'house' -> 'exact' (q=0),
                 geo_precision 'street' -> 'fuzzy_street' (q=2).
"""
import hashlib
import json
import os
import re
from collections import defaultdict

BASE = os.path.expanduser('~/workspace/lehmann-map')
SITE = os.path.join(BASE, 'web', 'site')
DATA = os.path.join(SITE, 'data38h')
SHARD = 1000

os.makedirs(os.path.join(DATA, 'records'), exist_ok=True)

def parse_name(raw):
    """Best-effort split of OCR name into (surname, given)."""
    t = (raw or '').strip()
    # strip obvious OCR garbage prefixes
    t = re.sub(r'^[\d\W_‚‘’“”"()\[\]{}]+', '', t).strip()
    if not t:
        return '', ''
    if ',' in t:
        # "Surname, Given" format
        parts = t.split(',', 1)
        return parts[0].strip(), parts[1].strip()
    toks = t.split()
    if len(toks) >= 2:
        last = toks[-1]
        # given name heuristic: short token, initial with period, or capitalized word
        if (len(last) <= 4 and (last.endswith('.') or last[0].isupper())) or \
           (last.endswith('.') and len(last) <= 6):
            return ' '.join(toks[:-1]), last
    return t, ''

def fold(t):
    """Lowercase + umlaut fold for search tokens."""
    t = (t or '').lower()
    t = t.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    return t

# ---- load geocoded records -----------------------------------------------
records = []  # (rec_dict)
seen_addr = defaultdict(list)
n_in = 0
for line in open(os.path.join(BASE, 'parsed_ivteil_geocoded.jsonl'), encoding='utf-8'):
    d = json.loads(line)
    n_in += 1
    lat, lon = d.get('lat'), d.get('lon')
    if lat is None or lon is None:
        continue
    st = d.get('street_clean') or ''
    hn = str(d.get('house_number') or '')
    if d.get('house_letter'):
        hn += d['house_letter']
    if not st or not hn:
        continue
    s, g = parse_name(d.get('name'))
    prec = d.get('geo_precision') or ''
    m = 'exact' if prec == 'house' else 'fuzzy_street'
    rec = {
        's': s, 'g': g,
        'o': (d.get('occupation') or '').strip() or None,
        'st': st, 'hn': hn,
        'd': d.get('district') or '',
        'm': m,
        'la': lat, 'lo': lon,
        'pg': d.get('page_id') or '',
    }
    records.append(rec)

print(f'input: {n_in}, geocoded with address: {len(records)}')

# ---- shard records --------------------------------------------------------
n_shards = (len(records) + SHARD - 1) // SHARD
for si in range(n_shards):
    chunk = records[si*SHARD:(si+1)*SHARD]
    out = {}
    for j, r in enumerate(chunk):
        gid = si*SHARD + j
        out[str(gid)] = r
    with open(os.path.join(DATA, 'records', f'r{si:04d}.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
print(f'shards: {n_shards}')

# ---- points.geojson (one pin per address) ---------------------------------
# Group by (street, house_number, coord) so street-precision records
# don't collapse entire streets into one pin.
groups = {}
for gid, r in enumerate(records):
    key = (r['st'], r['hn'], round(r['lo'], 6), round(r['la'], 6))
    g = groups.setdefault(key, [[], [0, 0, 0], r['lo'], r['la']])
    g[0].append(gid)
    q = 0 if r['m'] == 'exact' else 2
    g[1][q] += 1

feats = []
for (st, hn, lo, la), (idxs, qc, x, y) in groups.items():
    best = 0 if qc[0] else (1 if qc[1] else 2)
    feats.append('{"type":"Feature","geometry":{"type":"Point","coordinates":[%s,%s]},'
                 '"properties":{"m":[%s],"q":%d,"qc":[%d,%d,%d]}}'
                 % (x, y, ','.join(map(str, idxs)), best, qc[0], qc[1], qc[2]))
geojson = '{"type":"FeatureCollection","features":[' + ','.join(feats) + ']}'
with open(os.path.join(DATA, 'points.geojson'), 'w', encoding='utf-8') as f:
    f.write(geojson)
n_pins = len(groups)
print(f'points.geojson: {n_pins} pins, {len(records)} residents, {len(geojson)/1e6:.1f} MB')

# ---- search.idx.json ------------------------------------------------------
# tokens from street, surname, given, occupation -> record ids
idx = defaultdict(set)
for gid, r in enumerate(records):
    toks = set()
    for field in (r['st'], r['s'], r['g'], r['o']):
        for tok in re.split(r'[^a-zäöüß]+', fold(field)):
            if len(tok) >= 3:
                toks.add(tok)
    # also index "street housenumber" combos like "eblinggasse 23"
    hn_tok = fold(r['hn']).strip()
    if hn_tok:
        toks.add(fold(r['st']).replace(' ', '') + hn_tok)
    for t in toks:
        idx[t].add(gid)

idx_json = {k: sorted(v) for k, v in idx.items()}
with open(os.path.join(DATA, 'search.idx.json'), 'w', encoding='utf-8') as f:
    json.dump(idx_json, f, ensure_ascii=False)
print(f'search.idx.json: {len(idx_json)} tokens')

# ---- meta.json ------------------------------------------------------------
with open(os.path.join(DATA, 'meta.json'), 'w', encoding='utf-8') as f:
    json.dump({'year': '1938h', 'label': '1938 Houses', 'records': len(records),
               'pins': n_pins, 'shards': n_shards, 'tokens': len(idx_json)}, f)
print('done')
