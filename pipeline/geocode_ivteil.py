#!/usr/bin/env python3
"""Geocode IV. Teil parsed records using Band 1 address coordinates.

1. Builds (district, street, house) -> (lat, lon) from Band 1 records.
2. Applies street normalization to IV records.
3. Outputs parsed_ivteil_geocoded.jsonl with street_clean, lat, lon.
"""
import json, os, re
from collections import Counter, defaultdict

def canon_street(s):
    s = s.strip()
    # expand Band 1 abbreviations: 'Eßlingg.' -> 'Eßlinggasse', 'Ybbsstr.' -> 'Ybbsstrasse'
    # (match literal period; \b fails on '...gg.' since no boundary before final g)
    s = re.sub(r'str\.\s*$', 'strasse', s, flags=re.I)
    s = re.sub(r'g\.\s*$', 'gasse', s, flags=re.I)
    s = re.sub(r'pl\.\s*$', 'platz', s, flags=re.I)
    s = re.sub(r'ring\.\s*$', 'ring', s, flags=re.I)
    s = s.lower()
    s = s.replace('ß','ss').replace('ä','ae').replace('ö','oe').replace('ü','ue')
    s = s.replace('ftr.', 'str.').replace('ſtr.', 'str.')
    s = re.sub(r'[^a-z]', '', s)
    return s

def canon_district(d):
    return d.strip().upper()

def canon_house(h, hl=''):
    h = (h or '').strip()
    # numeric part
    m = re.match(r'(\d+)', h)
    num = m.group(1) if m else ''
    letter = (hl or '').strip().upper()
    # also extract letter suffix from house like "12A"
    m2 = re.match(r'\d+\s*([A-Z])', h.upper())
    if m2 and not letter:
        letter = m2.group(1)
    return num + letter

# --- Build Band 1 address DB ---
# Key on (street, house) only; district from parser is unreliable.
# If multiple districts have same street+house, take the most common coord.
addr_coords = defaultdict(list)
street_coords = defaultdict(list)  # street-level fallback
os.chdir('/home/hatch/workspace/VienneseDataCrunch')
n_rec = 0
for fn in sorted(os.listdir('data/records')):
    d = json.load(open('data/records/'+fn))
    for k, r in d.items():
        if not r.get('la'): continue
        n_rec += 1
        sk = canon_street(r.get('st',''))
        hk = canon_house(r.get('hn',''))
        if sk and hk:
            addr_coords[(sk, hk)].append((r['la'], r['lo'], canon_district(r.get('d',''))))
        if sk:
            street_coords[sk].append((r['la'], r['lo']))
print(f'Band 1 records with coords: {n_rec}, unique addr keys: {len(addr_coords)}, streets: {len(street_coords)}')

def centroid(pts):
    clusters = Counter((round(la,4), round(lo,4)) for la, lo in pts)
    return clusters.most_common(1)[0][0]

# majority vote per key
addr_db = {}
for key, pts in addr_coords.items():
    (cla, clo), _ = Counter((round(la,4), round(lo,4)) for la, lo, _ in pts).most_common(1)[0]
    dists = Counter(dd for la, lo, dd in pts if round(la,4)==cla and round(lo,4)==clo)
    addr_db[key] = (cla, clo, dists.most_common(1)[0][0])
street_db = {sk: centroid(pts) for sk, pts in street_coords.items()}
print(f'address DB: {len(addr_db)} keys, street DB: {len(street_db)} streets')

# --- Normalize + geocode IV records ---
os.chdir('/home/hatch/workspace/lehmann-map')
norm = json.load(open('street_normalization.json'))

# OSM caches: house-level (street|house -> [lat, lon]) and street-level
osm_house = json.load(open('osm_house_cache.json'))
osm_street_exact = json.load(open('osm_street_cache.json')).get('exact', {})
n_osm_house = 0

n_total = n_street = n_geo = n_geo_street = 0
n_no_house = 0
out = open('parsed_ivteil_geocoded.jsonl', 'w')
unmatched_streets = Counter()
unmatched_addr = Counter()
for line in open('parsed_ivteil.jsonl'):
    r = json.loads(line)
    n_total += 1
    ns = r.get('street','').strip()
    clean = norm.get(ns)
    r['street_clean'] = clean or ''
    if clean:
        n_street += 1
        sk = canon_street(clean)
        hk = canon_house(r.get('house_number',''), r.get('house_letter',''))
        key = (sk, hk)
        if not hk:
            n_no_house += 1
        # 1. OSM house cache (exact street|house)
        osm_key = f"{clean}|{hk}"
        if hk and osm_key in osm_house:
            la, lo = osm_house[osm_key]
            r['lat'] = la; r['lon'] = lo
            r['geo_precision'] = 'house'
            r['geo_source'] = 'osm'
            n_geo += 1
            n_osm_house += 1
        elif key in addr_db:
            la, lo, dd = addr_db[key]
            r['lat'] = la; r['lon'] = lo
            r['district_db'] = dd
            r['geo_precision'] = 'house'
            r['geo_source'] = 'band1'
            n_geo += 1
        elif clean in osm_street_exact:
            # OSM street-level
            e = osm_street_exact[clean]
            r['lat'] = e['lat']; r['lon'] = e['lon']
            r['geo_precision'] = 'street'
            r['geo_source'] = 'osm'
            n_geo_street += 1
        elif sk in street_db:
            # Band 1 street-level fallback (no exact house match)
            la, lo = street_db[sk]
            r['lat'] = la; r['lon'] = lo
            r['geo_precision'] = 'street'
            r['geo_source'] = 'band1'
            n_geo_street += 1
        else:
            unmatched_addr[(clean, hk)] += 1
    else:
        if ns:
            unmatched_streets[ns] += 1
    out.write(json.dumps(r, ensure_ascii=False) + '\n')
out.close()

print(f'\ntotal: {n_total}')
print(f'with street_clean: {n_street} ({n_street/n_total*100:.1f}%)')
print(f'geocoded (house-level): {n_geo} ({n_geo/n_total*100:.1f}% of total)')
print(f'geocoded (street-level fallback): {n_geo_street} ({n_geo_street/n_total*100:.1f}% of total)')
print(f'total with coords: {n_geo + n_geo_street} ({(n_geo+n_geo_street)/n_total*100:.1f}%)')
print(f'  from OSM house cache: {n_osm_house}')
print(f'no house number: {n_no_house}')
print('\n--- top unmatched (district, street, house) ---')
for k, c in unmatched_addr.most_common(20):
    print(f'{c:5d} {k}')
print('\n--- unmatched street strings ---')
for s, c in unmatched_streets.most_common():
    print(f'{c:6d} {s!r}')
