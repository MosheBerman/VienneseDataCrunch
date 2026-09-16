#!/usr/bin/env python3
"""Build the Mapbox GL JS version of the Lehmann 1938 web map (v2).

Reads ~/workspace/lehmann-map/full1938_v3_geocoded.jsonl and writes a
self-contained static site to ~/workspace/lehmann-map/web/site/ :
  index.html (JS inlined, atomic shell), sw.js, data/points.<sha1>.geojson
Reuses data/records/*.json, data/search.idx.json, data/meta.json from
rebuild_shards.py (line-index id scheme, matching the GeoJSON member ids).

MAPBOX_TOKEN placeholder "__MAPBOX_TOKEN__" in index.html must be replaced
with a real public token before deploy.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone

BASE = os.path.expanduser('~/workspace/lehmann-map')
SITE = os.path.join(BASE, 'web', 'site')
DATA = os.path.join(SITE, 'data')
MBGL = '3.30.0'

# ---- scan-page → pageview-ID map (Wienbibliothek; not a clean formula) ----
try:
    with open(os.path.join(BASE, 'scanpage_to_pageview.json'), encoding='utf-8') as f:
        _scanpv = json.load(f)
except OSError:
    _scanpv = {}
SCAN_PV_JS = 'const SCAN_PV={' + ','.join(
    '%d:%d' % (int(k), int(v)) for k, v in sorted(_scanpv.items(), key=lambda kv: int(kv[0]))
) + '};'
if _scanpv:
    print(f'scan map: {len(_scanpv)} pages')

# ---- site config: scan viewer + correction form (may be partially empty) ----
try:
    with open(os.path.join(BASE, 'site_config.json'), encoding='utf-8') as f:
        _cfg = json.load(f)
except OSError:
    _cfg = {}
VIEWER_URL = (_cfg.get('viewer') or {}).get('page_url') or ''
VIEWER_LABEL = (_cfg.get('viewer') or {}).get('label') or 'Original scan'
CORRECT_PREFILL = (_cfg.get('correction_form') or {}).get('prefill_url') or ''

os.makedirs(DATA, exist_ok=True)

# ---- points.geojson (one pin per address; members grouped) --------------------
entries = []
with open(os.path.join(BASE, 'full1938_v3_geocoded.jsonl'), encoding='utf-8') as f:
    for i, line in enumerate(f):
        e = json.loads(line)
        if e.get('lat') is None:
            continue
        gm = e.get('geo_match') or ''
        q = 0 if gm == 'exact' else (2 if gm.startswith('fuzzy_street') else 1)
        entries.append((i, round(e['lon'], 6), round(e['lat'], 6), q))

groups = {}
for i, lo, la, q in entries:
    g = groups.setdefault((lo, la), [[], [0, 0, 0]])
    g[0].append(i)
    g[1][q] += 1

feats = []
for (lo, la), (idxs, qc) in groups.items():
    best = 0 if qc[0] else (1 if qc[1] else 2)
    feats.append('{"type":"Feature","geometry":{"type":"Point","coordinates":[%s,%s]},'
                 '"properties":{"m":[%s],"q":%d,"qc":[%d,%d,%d]}}'
                 % (lo, la, ','.join(map(str, idxs)), best, qc[0], qc[1], qc[2]))
geojson = '{"type":"FeatureCollection","features":[' + ','.join(feats) + ']}'
gh = hashlib.sha1(geojson.encode('utf-8')).hexdigest()[:12]
points_name = f'points.{gh}.geojson'
with open(os.path.join(DATA, points_name), 'w', encoding='utf-8') as f:
    f.write(geojson)
for fn in os.listdir(DATA):  # drop stale hashed copies from earlier builds
    if re.fullmatch(r'points\.[0-9a-f]{12}\.geojson', fn) and fn != points_name:
        os.remove(os.path.join(DATA, fn))
n_pins = len(groups)
print(f'{points_name}: {n_pins} pins, {len(entries)} people, {len(geojson)/1e6:.1f} MB')

# ---- index.html -----------------------------------------------------------
_src_btn = ''
_home_url = (_cfg.get('viewer') or {}).get('home_url') or ''
if _home_url:
    _src_btn = ('<a id="srcBtn" href="%s" target="_blank" rel="noopener">%s</a>'
                % (_home_url.replace('&', '&amp;'), VIEWER_LABEL))
_src_about = ''
if _home_url:
    _src_about = ('<h3>Source</h3><p>The directory was scanned from the 1938 volume held by the '
                  'Wienbibliothek im Rathaus. <a href="%s" target="_blank" rel="noopener">Browse the original '
                  'scan</a> page by page.</p>' % _home_url.replace('&', '&amp;'))
index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Lehmann 1938 \u00b7 Vienna Address Map</title>
<script src="https://api.mapbox.com/mapbox-gl-js/v{MBGL}/mapbox-gl.js"></script>
<link href="https://api.mapbox.com/mapbox-gl-js/v{MBGL}/mapbox-gl.css" rel="stylesheet">
<style>
html,body{{margin:0;padding:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}}
#map{{position:absolute;top:0;bottom:0;width:100%;}}
header{{position:absolute;top:10px;left:10px;right:10px;z-index:5;display:flex;gap:8px;align-items:center;flex-wrap:wrap;pointer-events:none;}}
header>*{{pointer-events:auto;}}
.brand{{background:#111827;color:#fff;padding:8px 14px;border-radius:10px;font-weight:700;font-size:15px;box-shadow:0 2px 8px rgba(0,0,0,.25);white-space:nowrap;}}
.brand small{{font-weight:400;color:#9ca3af;}}
.brand b{{color:#ffd97a;}}
#q{{flex:1;min-width:140px;max-width:340px;padding:9px 12px;border:1px solid #d1d5db;border-radius:10px;font-size:15px;box-shadow:0 2px 8px rgba(0,0,0,.18);}}
#flt,#aboutBtn{{padding:9px 12px;border:1px solid #d1d5db;border-radius:10px;font-size:14px;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.18);cursor:pointer;}}
#aboutBtn{{font-weight:600;}}
#srcBtn{{padding:9px 12px;border:1px solid #d1d5db;border-radius:10px;font-size:14px;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,.18);cursor:pointer;color:#111;text-decoration:none;}}
.pp-links{{margin-top:4px;font-size:12px;color:#6b7280;}}
.pp-links a{{color:#2563eb;text-decoration:none;}}
#results{{position:absolute;top:56px;left:10px;z-index:6;background:#fff;border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,.25);max-width:360px;max-height:50vh;overflow:auto;display:none;}}
#results div{{padding:9px 12px;border-bottom:1px solid #f3f4f6;cursor:pointer;font-size:14px;}}
#results div:last-child{{border-bottom:none;}}
#results div:hover{{background:#f9fafb;}}
#results .r-sub{{color:#6b7280;font-size:12px;}}
footer{{position:absolute;left:10px;bottom:10px;z-index:5;background:rgba(17,24,39,.85);color:#e5e7eb;padding:6px 12px;border-radius:8px;font-size:12px;}}
footer b{{color:#fff;}}
.pp{{font-size:14px;line-height:1.45;min-width:180px;}}
.pp-name{{font-weight:700;font-size:15px;}}
.pp-occ{{color:#4b5563;font-style:italic;}}
.pp-addr{{margin-top:2px;}}
.pp-meta{{color:#6b7280;font-size:12px;margin-top:4px;}}
.pp-list{{max-height:230px;overflow:auto;margin-top:6px;border-top:1px solid #f3f4f6;}}
.pp-row{{padding:6px 2px;border-bottom:1px solid #f3f4f6;}}
.pp-row:last-child{{border-bottom:none;}}
.pp-row.hl{{background:#eff6ff;border-radius:6px;padding:6px;}}
.pp-more{{color:#6b7280;font-size:12px;margin-top:4px;}}
#aboutOverlay{{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:20;display:none;align-items:center;justify-content:center;padding:18px;}}
#aboutBox{{background:#fff;border-radius:14px;max-width:620px;max-height:85vh;overflow:auto;padding:24px 26px;box-shadow:0 8px 40px rgba(0,0,0,.35);}}
#aboutBox h2{{margin:0 0 4px;font-size:20px;}}
#aboutBox h3{{margin:16px 0 6px;font-size:15px;}}
#aboutBox p{{font-size:14px;line-height:1.6;color:#1f2937;margin:8px 0;}}
#aboutClose{{float:right;border:none;background:#f3f4f6;border-radius:8px;padding:6px 12px;font-size:14px;cursor:pointer;}}
@media (max-width:640px){{.brand{{font-size:13px;}}#q{{font-size:14px;}}}}
.spin{{width:34px;height:34px;border-radius:50%;border:4px solid rgba(0,0,0,.12);border-top-color:#1a73e8;animation:spn .8s linear infinite;}}
.spin.sm{{width:20px;height:20px;border-width:3px;}}
@keyframes spn{{to{{transform:rotate(360deg);}}}}
#boot{{position:fixed;inset:0;z-index:50;display:flex;flex-direction:column;gap:14px;align-items:center;justify-content:center;background:#e9e5d9;color:#4b5563;font-size:14px;transition:opacity .4s;}}
#boot.gone{{opacity:0;pointer-events:none;}}
.r-load{{display:flex;justify-content:center;padding:14px !important;cursor:default !important;}}
.pp-load{{display:flex;justify-content:center;padding:18px 34px;}}
</style>
</head>
<body>
<div id="map"></div>
<div id="boot"><div class="spin"></div><div>Loading {len(entries):,} people at {n_pins:,} addresses…</div></div>
<header>
  <div class="brand">Lehmann <b>1938</b> <small>\u00b7 Vienna</small></div>
  <input id="q" type="search" placeholder="Surname, street, occupation\u2026" autocomplete="off">
  <select id="flt">
    <option value="all">All pins</option>
    <option value="reg">Registry or better</option>
    <option value="exact">Exact only</option>
  </select>
  <button id="aboutBtn">About</button>
  {_src_btn}
</header>
<div id="results"></div>
<footer><b id="count">\u2014</b> people \u00b7 <b id="acount">\u2014</b> addresses \u00b7 blue exact \u00b7 purple registry \u00b7 amber fuzzy</footer>
<div id="aboutOverlay"><div id="aboutBox">
<button id="aboutClose">Close</button>
<h2>About this map</h2>
<p>Every pin is a Vienna address with one or more people or businesses listed in the alphabetical residents' directory (Band&nbsp;1) of <i>Lehmann's Wohnungsanzeiger</i> for 1938 \u2014 Vienna's address book on the eve of World War&nbsp;II. Of 490,781 entries, 127,308 could be matched to a street address and placed on the modern map as {n_pins:,} pins.</p>
<h3>How it was built</h3>
<p>The 1,644-page scan was rendered page by page, split into columns, and OCR'd (Tesseract with a Fraktur model). A parsing pipeline extracted names, occupations and addresses, stripped page headers, footers and advertisements, and normalized historical street abbreviations. Each address was then joined against the City of Vienna's official address registry (\u201cAdressen Standorte Wien\u201d, CC&nbsp;BY&nbsp;4.0). Exact matches are blue, registry matches with a number fallback are purple, fuzzy street matches are amber.</p>
<h3>The AI part</h3>
<p>This pipeline was built by Muse by Meta, an AI research assistant, working with Moshe Berman. The agent wrote the OCR, parsing and geocoding code, ran the batches, validated samples against the page scans, and built this site. Every stage reported measured numbers \u2014 match rates, not adjectives \u2014 and uncertain matches are flagged on the map rather than hidden.</p>
<h3>Caveats</h3>
<p>OCR misreads names; some 1938 streets were renamed or no longer exist; amber pins are approximate. Absence of a pin doesn't mean absence from the book \u2014 only 48.7% of addressed entries matched the modern registry.</p>
{_src_about}
</div></div>
<script>window.MAPBOX_TOKEN="__MAPBOX_TOKEN__";</script>
<script>__APP_JS__</script>
</body>
</html>
"""

# ---- app.js ---------------------------------------------------------------
app_js = r"""'use strict';
mapboxgl.accessToken = window.MAPBOX_TOKEN;
const map = new mapboxgl.Map({
  container: 'map',
  style: 'mapbox://styles/mapbox/light-v11',
  center: [16.37, 48.208],
  zoom: 10.5,
  maxBounds: [[15.9, 47.9], [16.9, 48.45]]
});
map.addControl(new mapboxgl.NavigationControl(), 'bottom-right');

let allFeatures = [];
let featByRec = new Map();
let keepIdx = [0, 1, 2];
const shardCache = {};
const qCode = m => m === 'exact' ? 0 : (m && m.indexOf('fuzzy_street') === 0 ? 2 : 1);
// Per-record links: scan viewer page template (with {pageview} = Wienbibliothek
// pageview ID) and correction form prefill base (entry id appended URL-encoded).
// Empty when unconfigured. SCAN_PV maps 1-based scan page -> pageview ID.
const VIEWER_URL = "__VIEWER_URL__";
const CORRECT_URL = "__CORRECT_URL__";
__SCAN_PV_JS__
function recLinks(r){
  let links = '';
  const _pv = (r.pg != null) ? SCAN_PV[r.pg + 1] : null;
  if (VIEWER_URL && _pv)
    links += '<a href="' + VIEWER_URL.split('{pageview}').join(_pv) + '" target="_blank" rel="noopener">View in original</a>';
  if (CORRECT_URL && r._id != null)
    links += (links ? ' \u00b7 ' : '') + '<a href="' + CORRECT_URL + encodeURIComponent('1938:' + r._id) + '" target="_blank" rel="noopener">Suggest correction</a>';
  return links ? '<div class="pp-links">' + links + '</div>' : '';
}
let searchIdx = null;
let searchKeys = null; // [rawKey, foldedKey] pairs, built lazily on first search
const foldUmlaut = s => s.replace(/ſ/g, 's').replace(/ä/g, 'a').replace(/ö/g, 'o').replace(/ü/g, 'u').replace(/ß/g, 's').replace(/ss/g, 's');
// Given-name spelling variants: the book's spelling isn't always the family's
// (e.g. Josef Bermann is listed as "Jossel Bermann" in 1938). Variant tokens
// match at half weight so exact spellings still rank first.
const NAME_VAR = {josef: ['jossel', 'josel'], jossel: ['josef', 'josel'], josel: ['josef', 'jossel']};
function levLim(a, b, lim) {
  if (a === b) return 0;
  let n = a.length, m = b.length;
  if (Math.abs(n - m) > lim) return lim + 1;
  if (n > m) { const t = a; a = b; b = t; const u = n; n = m; m = u; }
  let prev = new Array(n + 1);
  for (let i = 0; i <= n; i++) prev[i] = i;
  for (let j = 1; j <= m; j++) {
    const cur = new Array(n + 1);
    cur[0] = j;
    let rowMin = j;
    const bj = b.charCodeAt(j - 1);
    for (let i = 1; i <= n; i++) {
      const cost = a.charCodeAt(i - 1) === bj ? 0 : 1;
      const v = Math.min(prev[i] + 1, cur[i - 1] + 1, prev[i - 1] + cost);
      cur[i] = v;
      if (v < rowMin) rowMin = v;
    }
    if (rowMin > lim) return lim + 1;
    prev = cur;
  }
  return prev[n];
}
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const qLabel = m => {
  if (m === 'exact') return 'exact registry match';
  if (!m) return 'fuzzy street match';
  if (m.indexOf('district_fb') === 0) return 'registry match \u00b7 district fallback';
  if (m.indexOf('range_in') === 0 || m.indexOf('wl_range') === 0) return 'registry match \u00b7 number range';
  if (m === 'alpha_fallback') return 'alphabetical fallback';
  return 'fuzzy street match';
};

map.on('load', async () => {
  const gj = await (await fetch('__POINTS_GEOJSON__')).json();
  allFeatures = gj.features;
  for (const f of allFeatures) for (const id of f.properties.m) featByRec.set(id, f);
  map.addSource('places', {type: 'geojson', data: gj, cluster: true, clusterMaxZoom: 14, clusterRadius: 55});

  map.addLayer({id: 'clusters', type: 'circle', source: 'places', filter: ['has', 'point_count'],
    paint: {
      'circle-color': ['step', ['get', 'point_count'], '#93c5fd', 100, '#60a5fa', 750, '#2563eb'],
      'circle-radius': ['step', ['get', 'point_count'], 16, 100, 23, 750, 31],
      'circle-stroke-width': 2, 'circle-stroke-color': '#fff', 'circle-opacity': 0.92}});
  map.addLayer({id: 'cluster-count', type: 'symbol', source: 'places', filter: ['has', 'point_count'],
    layout: {'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12,
             'text-font': ['DIN Pro Medium', 'Arial Unicode MS Bold']},
    paint: {'text-color': '#fff'}});
  map.addLayer({id: 'unclustered-point', type: 'circle', source: 'places', filter: ['!', ['has', 'point_count']],
    paint: {
      'circle-color': ['match', ['get', 'q'], 0, '#2563eb', 1, '#7c3aed', 2, '#d97706', '#2563eb'],
      'circle-radius': 4.5, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#fff', 'circle-opacity': 0.95}});

  const TAP_R = window.matchMedia && matchMedia('(pointer: coarse)').matches ? 44 : 14;
  function near(point, layer, r) {
    const b = [[point.x - r, point.y - r], [point.x + r, point.y + r]];
    return map.queryRenderedFeatures(b, {layers: [layer]});
  }
  map.on('click', async e => {
    const c = near(e.point, 'clusters', TAP_R)[0];
    if (c) {
      map.getSource('places').getClusterExpansionZoom(c.properties.cluster_id, (err, zoom) => {
        if (err) return;
        map.easeTo({center: c.geometry.coordinates, zoom: zoom, duration: 550});
      });
      return;
    }
    const f = near(e.point, 'unclustered-point', TAP_R)[0];
    if (!f) return;
    openGroupPopup(f, null);
  });
  for (const lyr of ['clusters', 'unclustered-point']) {
    map.on('mouseenter', lyr, () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', lyr, () => map.getCanvas().style.cursor = '');
  }
  updateCount(allFeatures);
  const hideBoot = () => $('boot').classList.add('gone');
  map.once('idle', hideBoot);
  setTimeout(hideBoot, 12000);
});

function updateCount(feats){
  let n = 0;
  for (const f of feats) { const qc = f.properties.qc; for (const k of keepIdx) n += qc[k]; }
  $('count').textContent = n.toLocaleString('en-US');
  $('acount').textContent = feats.length.toLocaleString('en-US');
}

$('flt').addEventListener('change', e => {
  const v = e.target.value;
  keepIdx = v === 'all' ? [0, 1, 2] : v === 'reg' ? [0, 1] : [0];
  const feats = allFeatures.filter(f => { const qc = f.properties.qc; return keepIdx.some(k => qc[k] > 0); });
  map.getSource('places').setData({type: 'FeatureCollection', features: feats});
  updateCount(feats);
});

function popupHTML(r){
  const q = qLabel(r.m);
  let h = '<div class="pp"><div class="pp-name">' + esc(r.s || '') + (r.g ? ', ' + esc(r.g) : '') + '</div>';
  if (r.o) h += '<div class="pp-occ">' + esc(r.o) + '</div>';
  h += '<div class="pp-addr">' + esc(r.st || '') + ' ' + esc(r.hn || '') +
       (r.u ? ' \u00b7 ' + esc(r.u) : '') + ', ' + esc(r.d || '') + '. Bezirk</div>';
  h += '<div class="pp-meta">1938 \u00b7 ' + esc(q) + '</div></div>';
  return h;
}

async function openGroupPopup(f, highlightId){
  const pop = new mapboxgl.Popup({offset: 14, maxWidth: '300px'})
    .setLngLat(f.geometry.coordinates)
    .setHTML('<div class="pp"><div class="pp-load"><div class="spin sm"></div></div></div>')
    .addTo(map);
  // NOTE: Mapbox encodes features to vector tiles internally, and non-scalar
  // properties (like our member-id array) come back JSON-stringified from
  // queryRenderedFeatures. Parse them back before use.
  let ids = f.properties.m;
  if (typeof ids === 'string') { try { ids = JSON.parse(ids); } catch (e) { ids = null; } }
  if (!Array.isArray(ids)) ids = (f.properties.i != null ? [f.properties.i] : []);
  const recs = (await Promise.all(ids.map(async id => {
    const r = await getRecord(id);
    if (r) r._id = id;
    return r;
  }))).filter(Boolean);
  if (!recs.length) { pop.remove(); return; }
  const shown = recs.filter(r => keepIdx.includes(qCode(r.m)));
  const list = (shown.length ? shown : recs).slice()
    .sort((a, b) => qCode(a.m) - qCode(b.m) || String(a.s).localeCompare(String(b.s)));
  const hidden = recs.length - list.length;
  const r0 = list[0];
  let h = '<div class="pp"><div class="pp-addr"><b>' + esc(r0.st || '') + ' ' + esc(r0.hn || '') +
          ', ' + esc(r0.d || '') + '. Bezirk</b></div><div class="pp-list">';
  for (const r of list) {
    h += '<div class="pp-row' + (highlightId !== null && r._id === highlightId ? ' hl' : '') + '">' +
      '<div class="pp-name">' + esc(r.s || '') + (r.g ? ', ' + esc(r.g) : '') + '</div>' +
      (r.o ? '<div class="pp-occ">' + esc(r.o) + '</div>' : '') +
      '<div class="pp-meta">' + (r.u ? esc(r.u) + ' \u00b7 ' : '') + '1938 \u00b7 ' + esc(qLabel(r.m)) + '</div>' +
      recLinks(r) + '</div>';
  }
  h += '</div>';
  if (hidden > 0) h += '<div class="pp-more">' + hidden + ' more resident' + (hidden > 1 ? 's' : '') + ' hidden by filter</div>';
  h += '</div>';
  pop.setHTML(h);
}

async function getRecord(id){
  const sh = 'r' + String(Math.floor(id / 1024)).padStart(4, '0');
  if (!shardCache[sh]) {
    try { shardCache[sh] = await (await fetch('data/records/' + sh + '.json')).json(); }
    catch (e) { return null; }
  }
  return shardCache[sh][String(id)] || null;
}

// ---- search -------------------------------------------------------------
let searchTimer = null;
$('q').addEventListener('input', e => {
  clearTimeout(searchTimer);
  const box = $('results');
  searchTimer = setTimeout(async () => {
    const q = e.target.value.trim().toLowerCase();
    if (q.length < 2) { box.style.display = 'none'; return; }
    if (!searchIdx) {
      box.innerHTML = '<div class="r-load"><div class="spin sm"></div></div>';
      box.style.display = 'block';
      try { searchIdx = await (await fetch('data/search.idx.json')).json(); }
      catch (err) { box.style.display = 'none'; return; }
    }
    const toks = q.split(/[^a-zäöüßſ]+/).filter(t => t.length >= 2).map(foldUmlaut);
    const xtoks = [];
    for (const t of toks) {
      xtoks.push([t, 1]);
      for (const v of (NAME_VAR[t] || [])) xtoks.push([v, 0.5]);
    }
    if (!searchKeys) searchKeys = Object.keys(searchIdx).map(k => [k, foldUmlaut(k)]);
    const hits = {};
    for (const [t, mul] of xtoks) {
      const thr = t.length <= 5 ? 1 : 2;
      for (let ki = 0; ki < searchKeys.length; ki++) {
        const key = searchKeys[ki][0], fk = searchKeys[ki][1];
        let w = 0;
        if (key === t) w = 8;
        else if (fk === t) w = 6;
        else if (fk.startsWith(t)) w = 4;
        else if (fk.indexOf(t) >= 0) w = 2;
        else if (Math.abs(fk.length - t.length) <= thr && levLim(fk, t, thr) <= thr) w = 1;
        if (!w) continue;
        const ids = searchIdx[key];
        for (let i = 0; i < ids.length; i++) {
          const id = ids[i];
          hits[id] = (hits[id] || 0) + w * mul;
        }
      }
    }
    const top = Object.entries(hits).sort((a, b) => b[1] - a[1]).slice(0, 8);
    if (!top.length) { box.innerHTML = '<div>No matches</div>'; box.style.display = 'block'; return; }
    box.innerHTML = '';
    for (const [id] of top) {
      const rec = await getRecord(+id);
      if (!rec) continue;
      const d = document.createElement('div');
      d.innerHTML = '<b>' + esc(rec.s || '') + '</b>' + (rec.g ? ', ' + esc(rec.g) : '') +
        '<div class="r-sub">' + esc(rec.st || '') + ' ' + esc(rec.hn || '') +
        (rec.d ? ' \u00b7 ' + esc(rec.d) + '. Bez.' : '') + (rec.o ? ' \u00b7 ' + esc(rec.o) : '') + '</div>';
      d.addEventListener('click', () => {
        box.style.display = 'none';
        const rid = +id;
        map.flyTo({center: [+rec.lo, +rec.la], zoom: 16, duration: 1400});
        map.once('moveend', () => {
          const f = featByRec.get(rid);
          if (f) openGroupPopup(f, rid);
          else new mapboxgl.Popup({offset: 14, maxWidth: '280px'})
            .setLngLat([+rec.lo, +rec.la]).setHTML(popupHTML(rec)).addTo(map);
        });
      });
      box.appendChild(d);
    }
    box.style.display = 'block';
  }, 220);
});
document.addEventListener('click', e => {
  if (!$('results').contains(e.target) && e.target.id !== 'q') $('results').style.display = 'none';
});

// ---- about --------------------------------------------------------------
$('aboutBtn').addEventListener('click', () => $('aboutOverlay').style.display = 'flex');
$('aboutClose').addEventListener('click', () => $('aboutOverlay').style.display = 'none');
$('aboutOverlay').addEventListener('click', e => {
  if (e.target.id === 'aboutOverlay') $('aboutOverlay').style.display = 'none';
});

// ---- service worker -----------------------------------------------------
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
"""
app_js = app_js.replace('__POINTS_GEOJSON__', 'data/' + points_name)
app_js = app_js.replace('__VIEWER_URL__', VIEWER_URL)
app_js = app_js.replace('__CORRECT_URL__', CORRECT_PREFILL)
app_js = app_js.replace('__SCAN_PV_JS__', SCAN_PV_JS)
index_html = index_html.replace('__APP_JS__', app_js)
open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8').write(index_html)

# ---- sw.js ----------------------------------------------------------------
BUILD_ID = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
sw_js = (
"const CACHE='lehmann1938-" + BUILD_ID + "';\n"
"const SHELL=['./','./index.html'];\n"
"self.addEventListener('install',e=>{\n"
"  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));\n"
"});\n"
"self.addEventListener('activate',e=>{\n"
"  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.indexOf('lehmann1938-')===0&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));\n"
"});\n"
"const isShell=u=>u.pathname.endsWith('/')||u.pathname.endsWith('/index.html');\n"
"self.addEventListener('fetch',e=>{\n"
"  const u=new URL(e.request.url);\n"
"  if(u.origin!==self.location.origin||e.request.method!=='GET')return; // mapbox tiles/cdn pass through\n"
"  if(isShell(u)){\n"
"    e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(CACHE).then(cc=>cc.put(e.request,c));return r;}).catch(()=>caches.match(e.request)));\n"
"    return;\n"
"  }\n"
"  e.respondWith(caches.match(e.request).then(hit=>{\n"
"    const net=fetch(e.request).then(r=>{\n"
"      if(r.ok){const c=r.clone();caches.open(CACHE).then(cc=>cc.put(e.request,c));}\n"
"      return r;\n"
"    }).catch(()=>hit);\n"
"    return hit||net;\n"
"  }));\n"
"});\n"
)
open(os.path.join(SITE, 'sw.js'), 'w', encoding='utf-8').write(sw_js)

# ---- remove dead files ------------------------------------------------------
for dead in ['worker.js', 'style.css', 'app.js',
             os.path.join('data', 'points.bin'), os.path.join('data', 'points.geojson')]:
    p = os.path.join(SITE, dead)
    if os.path.exists(p):
        os.remove(p)
        print('removed', dead)

print('site rebuilt for Mapbox GL JS v' + MBGL)
print('FILES:', sorted(os.listdir(SITE)))
