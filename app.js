'use strict';
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
let searchIdx = null;
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
  const gj = await (await fetch('data/points.geojson')).json();
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

  const TAP_R = window.matchMedia && matchMedia('(pointer: coarse)').matches ? 26 : 14;
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
  const ids = f.properties.m;
  const recs = (await Promise.all(ids.map(async id => {
    const r = await getRecord(id);
    if (r) r._id = id;
    return r;
  }))).filter(Boolean);
  if (!recs.length) return;
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
      '<div class="pp-meta">' + (r.u ? esc(r.u) + ' \u00b7 ' : '') + '1938 \u00b7 ' + esc(qLabel(r.m)) + '</div></div>';
  }
  h += '</div>';
  if (hidden > 0) h += '<div class="pp-more">' + hidden + ' more resident' + (hidden > 1 ? 's' : '') + ' hidden by filter</div>';
  h += '</div>';
  new mapboxgl.Popup({offset: 14, maxWidth: '300px'})
    .setLngLat(f.geometry.coordinates).setHTML(h).addTo(map);
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
      try { searchIdx = await (await fetch('data/search.idx.json')).json(); }
      catch (err) { return; }
    }
    const toks = q.split(/[^a-z\xe4\xf6\xfc\xdf\xc4\xd6\xdc\xdf]+/).filter(t => t.length >= 2);
    const hits = {};
    for (const t of toks) {
      const ids = searchIdx[t];
      if (!ids) continue;
      for (const id of ids) hits[id] = (hits[id] || 0) + 1;
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
