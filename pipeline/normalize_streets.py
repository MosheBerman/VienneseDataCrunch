#!/usr/bin/env python3
"""Normalize 87 noisy IV. Teil street strings -> clean canonical street names.

Strategy:
1. Cluster Band 1 street variants into canonical forms (most frequent wins).
2. Build trigram index over canonical forms.
3. For each noisy IV string: apply Fraktur fixups, then rank candidates by
   trigram overlap, then exact bounded Levenshtein on top candidates.
4. Report ambiguous/unmatched for manual review.
"""
import json, os, re
from collections import Counter

def canon(s):
    s = s.strip().lower()
    s = s.replace('ß','ss').replace('ä','ae').replace('ö','oe').replace('ü','ue')
    return s

def expand_abbrev(st):
    st = st.strip()
    st = st.replace('ftr.', 'str.').replace('ſtr.', 'str.').replace('ftr', 'str')
    st = re.sub(r'\bstr\.?\s*$', 'strasse', st, flags=re.I)
    st = re.sub(r'\bg\.?\s*$', 'gasse', st, flags=re.I)
    st = re.sub(r'\bpl\.?\s*$', 'platz', st, flags=re.I)
    st = re.sub(r'\bring\.?\s*$', 'ring', st, flags=re.I)
    return st

def fraktur_fix(s):
    s = s.strip()
    s = re.sub(r'\s+(er|im|O|Str)$', '', s)
    s = s.rstrip('-').strip()
    s = re.sub(r'^B', 'P', s)
    s = re.sub(r'^R', 'K', s)
    s = re.sub(r'^Sh', 'St', s)
    s = re.sub(r'^D', 'W', s)          # Fraktur W misread as D (Diefterweg -> W...)
    s = re.sub(r'^S([a-z])', lambda m: 'K'+m.group(1), s)  # Schureiweg -> K...
    s = s.replace('ftraf', 'strasse').replace('traf', 'strasse')
    s = re.sub(r'gafle$', 'gasse', s)
    s = re.sub(r'gafie$', 'gasse', s)
    s = re.sub(r'gaffe$', 'gasse', s)
    s = s.replace('gaff', 'gass')
    s = s.replace('ſ', 's')
    return s

def lev(a, b, limit):
    if abs(len(a)-len(b)) > limit: return limit+1
    if len(a) < len(b): a, b = b, a
    prev = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        cur = [i]; rowmin = i
        for j, cb in enumerate(b, 1):
            c = prev[j-1] if ca==cb else 1+min(prev[j-1], prev[j], cur[j-1])
            cur.append(c)
            if c < rowmin: rowmin = c
        if rowmin > limit: return limit+1
        prev = cur
    return prev[-1]

def trigrams(s):
    s = ' ' + s + ' '
    return {s[i:i+3] for i in range(len(s)-2)}

# --- Build canonical Band 1 street list ---
var_count = Counter()
os.chdir('/home/hatch/workspace/VienneseDataCrunch')
for fn in sorted(os.listdir('data/records')):
    d = json.load(open('data/records/'+fn))
    for k, r in d.items():
        st = r.get('st','').strip()
        if st:
            var_count[canon(expand_abbrev(st))] += 1

# cluster: canonical form = the highest-count variant; keep forms with count>=2
canonical = {c for c, n in var_count.items() if n >= 2}
print('canonical street forms:', len(canonical))

tri_index = {}
for c in canonical:
    for t in trigrams(c):
        tri_index.setdefault(t, []).append(c)

def candidates(fc, top=25):
    votes = Counter()
    for t in trigrams(fc):
        for c in tri_index.get(t, ()):
            votes[c] += 1
    return [c for c, _ in votes.most_common(top)]

# --- Match noisy streets ---
noisy = Counter()
for line in open('/home/hatch/workspace/lehmann-map/parsed_ivteil.jsonl'):
    r = json.loads(line)
    s = r.get('street','').strip()
    if s: noisy[s] += 1

result, ambiguous = {}, []
for n in sorted(noisy):
    fixed = fraktur_fix(n)
    fc = canon(fixed)
    if fc in canonical:
        result[n] = fc; continue
    cands = candidates(fc)
    lim = max(2, len(fc)//4 + 1)
    scored = []
    for c in cands:
        d = lev(fc, c, lim)
        if d <= lim: scored.append((d, c))
    scored.sort()
    if not scored:
        result[n] = None; ambiguous.append((n, 'NO MATCH', noisy[n])); continue
    d0, c0 = scored[0]
    if len(scored) > 1 and scored[1][0] <= d0 + 1 and scored[1][1] != c0:
        ambiguous.append((n, f"AMBIG: {c0}({var_count[c0]}) vs {scored[1][1]}({var_count[scored[1][1]]})", noisy[n]))
        result[n] = None
    else:
        result[n] = c0

os.chdir('/home/hatch/workspace/lehmann-map')
json.dump(result, open('street_normalization.json','w'), ensure_ascii=False, indent=1)

print('\n--- UNMATCHED / AMBIGUOUS (sorted by record count) ---')
for n, why, cnt in sorted(ambiguous, key=lambda x: -x[2]):
    print(f"{cnt:6d} {n!r} -> {why}")

print('\nmapped:', sum(1 for v in result.values() if v), '/', len(result))
for n in sorted(result):
    v = result[n]
    if v and canon(fraktur_fix(n)) != v:
        print(f"{noisy[n]:6d} {n!r} -> {v!r}")
