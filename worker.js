/* Web Worker: loads points.bin, clusters with supercluster off the main thread. */
importScripts('https://unpkg.com/supercluster@8.0.1/dist/supercluster.min.js');

let index = null;
let pts = null;   // {n, ids, lats, lons, quals}
let qmax = 2;

function buildIndex() {
  const feats = [];
  const { n, ids, lats, lons, quals } = pts;
  for (let i = 0; i < n; i++) {
    if (quals[i] > qmax) continue;
    feats.push({
      type: 'Feature',
      properties: { id: ids[i], q: quals[i] },
      geometry: { type: 'Point', coordinates: [lons[i], lats[i]] },
    });
  }
  index = new Supercluster({ radius: 60, maxZoom: 16, minPoints: 2 });
  index.load(feats);
  return feats.length;
}

function query(msg) {
  const t0 = performance.now();
  const clusters = index.getClusters(msg.bbox, msg.zoom);
  postMessage({
    type: 'clusters', reqId: msg.reqId,
    clusters, ms: Math.round(performance.now() - t0),
  });
}

onmessage = (e) => {
  const d = e.data;
  if (d.type === 'init') {
    const buf = d.buffer;
    const n = new Uint32Array(buf, 0, 1)[0];
    pts = {
      n,
      ids: new Uint32Array(buf, 4, n),
      lats: new Float32Array(buf, 4 + 4 * n, n),
      lons: new Float32Array(buf, 4 + 8 * n, n),
      quals: new Uint8Array(buf, 4 + 12 * n, n),
    };
    const kept = buildIndex();
    postMessage({ type: 'ready', points: pts.n, kept });
  } else if (d.type === 'filter') {
    qmax = d.quality;
    const kept = buildIndex();
    postMessage({ type: 'filtered', kept });
    query(d);
  } else if (d.type === 'query') {
    query(d);
  } else if (d.type === 'expand') {
    try {
      const z = index.getClusterExpansionZoom(d.clusterId);
      postMessage({ type: 'expanded', reqId: d.reqId, zoom: z });
    } catch (err) { /* cluster gone after reindex */ }
  } else if (d.type === 'leaves') {
    // ids of points in a cluster, for "zoom to fit" on shift-click etc.
    try {
      const leaves = index.getLeaves(d.clusterId, 200);
      postMessage({ type: 'leaves', reqId: d.reqId,
        ids: leaves.map(f => f.properties.id) });
    } catch (err) {}
  }
};
