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
const shardCache = {};
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

  map.on('click', 'clusters', e => {
    const f = map.queryRenderedFeatures(e.point, {layers: ['clusters']})[0];
    if (!f) return;
    map.getSource('places').getClusterExpansionZoom(f.properties.cluster_id, (err, zoom) => {
      if (err) return;
      map.easeTo({center: f.geometry.coordinates, zoom: zoom, duration: 550});
    });
  });
  map.on('click', 'unclustered-point', async e => {
    const f = e.features && e.features[0];
    if (!f) return;
    const rec = await getRecord(f.properties.i);
    if (!rec) return;
    new mapboxgl.Popup({offset: 14, maxWidth: '280px'})
      .setLngLat(f.geometry.coordinates).setHTML(popupHTML(rec)).addTo(map);
  });
  for (const lyr of ['clusters', 'unclustered-point']) {
    map.on('mouseenter', lyr, () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', lyr, () => map.getCanvas().style.cursor = '');
  }
  updateCount(allFeatures.length);
});

function updateCount(n){ $('count').textContent = n.toLocaleString('en-US'); }

$('flt').addEventListener('change', e => {
  const v = e.target.value;
  const keep = v === 'all' ? null : v === 'reg' ? [0, 1] : [0];
  const feats = keep ? allFeatures.filter(f => keep.includes(f.properties.q)) : allFeatures;
  map.getSource('places').setData({type: 'FeatureCollection', features: feats});
  updateCount(feats.length);
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
        map.flyTo({center: [+rec.lo, +rec.la], zoom: 16, duration: 1400});
        map.once('moveend', () => {
          new mapboxgl.Popup({offset: 14, maxWidth: '280px'})
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
