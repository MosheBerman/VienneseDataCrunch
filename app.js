/* Lehmann 1938 map: Leaflet + canvas overlay, clustering in a Web Worker,
   data from a compact binary, record shards + search index on demand. */
(function () {
  'use strict';

  const DATA = 'data';
  const SHARD = 1024;
  const QCOLOR = ['#2563eb', '#7c3aed', '#d97706']; // exact, registry, fuzzy

  const map = L.map('map', { zoomControl: true, worldCopyJump: true });
  map.attributionControl.setPrefix(false);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd', maxZoom: 19,
  }).addTo(map);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }

  const statusEl = document.getElementById('status');
  const countEl = document.getElementById('count');
  const setStatus = (t) => { countEl.textContent = t; };

  // ---- canvas overlay -------------------------------------------------
  let clusters = [];       // last worker result
  let clusterZoom = 0;
  const canvas = L.DomUtil.create('canvas', 'lehmann-canvas');
  const ctx = canvas.getContext('2d');

  const overlay = L.Layer.extend({
    onAdd(m) {
      m.getPanes().overlayPane.appendChild(canvas);
      m.on('move', this._draw, this);
      m.on('moveend zoomend resize', this._request, this);
      this._reset();
      this._request();
    },
    onRemove(m) {
      m.getPanes().overlayPane.removeChild(canvas);
      m.off('move', this._draw, this);
      m.off('moveend zoomend resize', this._request, this);
    },
    _reset() {
      const size = map.getSize();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = size.x * dpr; canvas.height = size.y * dpr;
      canvas.style.width = size.x + 'px'; canvas.style.height = size.y + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
    },
    _request() { requestClusters(); },
    _draw() {
      this._reset();
      const dpr = window.devicePixelRatio || 1;
      void dpr;
      for (const c of clusters) {
        const p = map.latLngToContainerPoint([c.geometry.coordinates[1], c.geometry.coordinates[0]]);
        c._x = p.x; c._y = p.y;
        if (c.properties.cluster) {
          const n = c.properties.point_count;
          const r = 14 + Math.min(22, 6 * Math.log10(n));
          ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 7);
          ctx.fillStyle = 'rgba(30,30,34,0.88)'; ctx.fill();
          ctx.fillStyle = '#fff'; ctx.font = 'bold 12px sans-serif';
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillText(n > 999 ? (n / 1000).toFixed(1) + 'k' : n, p.x, p.y);
        } else {
          ctx.beginPath(); ctx.arc(p.x, p.y, 3.2, 0, 7);
          ctx.fillStyle = QCOLOR[c.properties.q] || QCOLOR[0];
          ctx.fill();
        }
      }
    },
  });
  const overlayInst = new overlay();

  // ---- worker ----------------------------------------------------------
  const worker = new Worker('worker.js');
  let reqId = 0, lastReq = 0;
  const pending = {};

  function requestClusters() {
    const z = map.getZoom();
    const b = map.getBounds().pad(0.5);
    const id = ++reqId; lastReq = id;
    worker.postMessage({ type: 'query', reqId: id, zoom: z,
      bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()] });
  }

  worker.onmessage = (e) => {
    const d = e.data;
    if (d.type === 'ready') {
      setStatus(d.points.toLocaleString() + ' addresses');
      overlayInst.addTo(map);
    } else if (d.type === 'clusters') {
      if (d.reqId !== lastReq) return;
      clusters = d.clusters;
      clusterZoom = map.getZoom();
      overlayInst._draw();
    } else if (d.type === 'filtered') {
      setStatus(d.kept.toLocaleString() + ' addresses');
    } else if (d.type === 'expanded') {
      const cb = pending[d.reqId]; delete pending[d.reqId];
      if (cb) cb(d.zoom);
    }
  };

  fetch(DATA + '/points.bin')
    .then((r) => { if (!r.ok) throw new Error('points.bin'); return r.arrayBuffer(); })
    .then((buf) => worker.postMessage({ type: 'init', buffer: buf }, [buf]))
    .catch(() => setStatus('failed to load data'));

  fetch(DATA + '/meta.json').then((r) => r.json()).then((m) => {
    const b = m.bounds; // [minlat, minlon, maxlat, maxlon]
    map.fitBounds([[b[0], b[1]], [b[2], b[3]]]);
  }).catch(() => map.setView([48.2082, 16.3738], 11));

  // ---- record shards ----------------------------------------------------
  const shardCache = {};
  function getRecord(id) {
    const s = Math.floor(id / SHARD);
    if (!shardCache[s]) {
      shardCache[s] = fetch(`${DATA}/records/r${String(s).padStart(4, '0')}.json`)
        .then((r) => { if (!r.ok) throw 0; return r.json(); });
    }
    return shardCache[s].then((recs) => recs[String(id)]);
  }

  const MATCH_LABEL = { exact: 'exact match', range_in: 'in official number range',
    range_endpoints: 'range endpoint', range_contains: 'contains range',
    district_fb: 'district fallback', letter_fb: 'letter-suffix fallback' };
  function matchLabel(m) {
    if (!m) return '';
    if (m === 'exact') return 'exact match';
    if (m.startsWith('fuzzy_street')) return 'fuzzy street match (OCR)';
    if (m.startsWith('district_fb')) return 'district fallback';
    return MATCH_LABEL[m] || m;
  }

  function popupHtml(r) {
    const addr = [r.st, r.hn].filter(Boolean).join(' ') +
      (r.u ? ', ' + r.u : '') + (r.d ? ', ' + r.d + '. Bezirk' : '');
    return `<div class="nm">${esc(r.s || '')}${r.g ? ', ' + esc(r.g) : ''}</div>` +
      (r.o ? `<div class="occ">${esc(r.o)}</div>` : '') +
      `<div class="addr">${esc(addr)}</div>` +
      `<div class="meta">1938 · ${esc(matchLabel(r.m))}</div>`;
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  // ---- clicking ----------------------------------------------------------
  map.on('click', (e) => {
    let best = null, bestD = 16;
    for (const c of clusters) {
      if (c._x === undefined) continue;
      const dx = c._x - e.containerPoint.x, dy = c._y - e.containerPoint.y;
      const dd = Math.hypot(dx, dy);
      if (dd < bestD) { bestD = dd; best = c; }
    }
    if (!best) return;
    if (best.properties.cluster) {
      const id = ++reqId;
      pending[id] = (z) => map.flyTo(e.latlng, Math.min(z, 18), { duration: 0.6 });
      worker.postMessage({ type: 'expand', reqId: id, clusterId: best.properties.cluster_id });
    } else {
      const id = best.properties.id;
      const ll = [best.geometry.coordinates[1], best.geometry.coordinates[0]];
      getRecord(id).then((r) => {
        if (r) L.popup({ maxWidth: 280 }).setLatLng(ll).setContent(popupHtml(r)).openOn(map);
      }).catch(() => {});
    }
  });

  // ---- quality filter -----------------------------------------------------
  document.getElementById('quality').addEventListener('change', (e) => {
    const q = parseInt(e.target.value, 10);
    const id = ++reqId; lastReq = id;
    const z = map.getZoom();
    const b = map.getBounds().pad(0.5);
    worker.postMessage({ type: 'filter', quality: q, reqId: id, zoom: z,
      bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()] });
  });

  // ---- search ---------------------------------------------------------------
  const input = document.getElementById('search');
  const resultsEl = document.getElementById('results');
  let searchIdx = null, searchLoading = null;

  function fold(s) {
    return (s || '').toLowerCase().replace(/ſ/g, 's')
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }
  function ensureIndex() {
    if (searchIdx) return Promise.resolve(searchIdx);
    if (!searchLoading) {
      setStatus('loading search…');
      searchLoading = fetch(DATA + '/search.idx.json').then((r) => r.json())
        .then((idx) => { searchIdx = idx; return idx; });
    }
    return searchLoading;
  }
  input.addEventListener('focus', () => { ensureIndex().then(() => setStatus('')); }, { once: true });

  let debounce = null;
  input.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(runSearch, 160);
  });
  document.addEventListener('click', (e) => {
    if (!document.getElementById('searchwrap').contains(e.target)) resultsEl.style.display = 'none';
  });

  function runSearch() {
    const q = fold(input.value.trim());
    if (q.length < 3) { resultsEl.style.display = 'none'; return; }
    ensureIndex().then((idx) => {
      const hits = new Map();
      for (const tok in idx) {
        if (tok.startsWith(q)) {
          for (const id of idx[tok]) {
            hits.set(id, (hits.get(id) || 0) + 1);
            if (hits.size > 400) break;
          }
        }
        if (hits.size > 400) break;
      }
      const top = [...hits.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
      if (!top.length) {
        resultsEl.innerHTML = '<div class="hit">No matches</div>';
        resultsEl.style.display = 'block';
        return;
      }
      // fetch the shards covering the top hits for display rows
      const need = [...new Set(top.map(([id]) => Math.floor(id / SHARD)))];
      Promise.all(need.map((s) => {
        if (!shardCache[s]) {
          shardCache[s] = fetch(`${DATA}/records/r${String(s).padStart(4, '0')}.json`).then((r) => r.json());
        }
        return shardCache[s];
      })).then((shards) => {
        const byId = {};
        shards.forEach((sh) => Object.assign(byId, sh));
        resultsEl.innerHTML = '';
        for (const [id] of top) {
          const r = byId[String(id)];
          if (!r) continue;
          const div = document.createElement('div');
          div.className = 'hit';
          div.innerHTML = `<div><b>${esc(r.s || '')}</b>${r.g ? ', ' + esc(r.g) : ''}</div>` +
            `<div class="sub">${esc([r.st, r.hn].filter(Boolean).join(' '))}${r.d ? ' · ' + r.d + '. Bez.' : ''}${r.o ? ' · ' + esc(r.o) : ''}</div>`;
          div.addEventListener('click', () => {
            resultsEl.style.display = 'none';
            map.flyTo([r.la, r.lo], 17, { duration: 0.8 });
            setTimeout(() => {
              L.popup({ maxWidth: 280 }).setLatLng([r.la, r.lo])
                .setContent(popupHtml(r)).openOn(map);
            }, 850);
          });
          resultsEl.appendChild(div);
        }
        resultsEl.style.display = 'block';
      });
    });
  }
})();
