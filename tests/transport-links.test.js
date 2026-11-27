// Deportation transport links: transports/links.json must only point at
// real directory records, and the rendering helpers in index.html must
// show the line for a linked record and nothing for any other record.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const links = JSON.parse(fs.readFileSync(path.join(ROOT, 'transports', 'links.json'), 'utf8'));
const YEAR_DIRS = {1938: 'data', 1939: 'data39', 1940: 'data40', 1941: 'data41', 1942: 'data42'};

test('every link points at an existing directory record and transport', () => {
  const shards = {};
  for (const [key, l] of Object.entries(links.links)) {
    const m = /^(\d{4}):(\d+)$/.exec(key);
    assert.ok(m, `key ${key} is <year>:<lineid>`);
    const dir = YEAR_DIRS[m[1]];
    assert.ok(dir, `year ${m[1]} is a production layer`);
    assert.ok(links.transports[l.t], `transport ${l.t} is described`);
    assert.ok(Number.isInteger(l.n) && l.n > 0, `${key} has a list number`);
    const shard = 'r' + String(Math.floor(+m[2] / 1000)).padStart(4, '0') + '.json';
    const f = path.join(ROOT, dir, 'records', shard);
    shards[f] = shards[f] || JSON.parse(fs.readFileSync(f, 'utf8'));
    assert.ok(shards[f][m[2]], `${key} exists in ${dir}/records/${shard}`);
  }
});

test('transport scans stay out of the repo', () => {
  const gi = fs.readFileSync(path.join(ROOT, '.gitignore'), 'utf8');
  assert.ok(gi.includes('/transports/**/*.jpg'), 'scan JPGs are ignored');
  assert.ok(gi.includes('/transports/**/*.png'), 'scan crops are ignored');
});

function loadHelpers(lang) {
  const start = html.indexOf('// ---- deportation transport links');
  const end = html.indexOf('// ---- corrections overlay');
  assert.ok(start > 0 && end > start, 'helper block found');
  const ctx = {
    LANG: lang, CUR_YEAR: '1940', Date, encodeURIComponent, String,
    fetch: () => Promise.resolve({ok: false}),
    esc: s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c])),
    isAddId: id => /^\d{4}:a\d+$/.test(String(id)),
    t: (k, v) => ({deportLine: '{transport}|{date}|{from}|{to}|{n}', deportSource: 'Source'}[k]
      .replace(/\{(\w+)\}/g, (_, x) => v && v[x] != null ? v[x] : '')),
  };
  vm.createContext(ctx);
  vm.runInContext(html.slice(start, end).replace('let TRANSPORTS', 'var TRANSPORTS') + '\nTRANSPORTS = __L;', Object.assign(ctx, {__L: links}));
  return ctx;
}

test('a linked record gets the deported line, others get nothing', () => {
  const h = loadHelpers('en');
  const out = h.deportLine({_id: 23953, _yr: '1938'});
  assert.ok(out.includes('pp-deport'), 'line rendered');
  assert.ok(out.includes('Transport 1|15 Feb 1941|Vienna|Opole|30'), out);
  assert.ok(out.includes('collections.arolsen-archives.org/en/document/130500826'), 'cites the Arolsen page');
  assert.equal(h.deportLine({_id: 23953, _yr: '1940'}), '', 'same line id in another year is not linked');
  assert.equal(h.deportLine({_id: '1938:a12'}), '', 'added addresses are never linked');
  assert.equal(h.deportLine({}), '');
});

test('follow views show the first linked stop', () => {
  const h = loadHelpers('de');
  const stops = [{year: '1938', id: 23953}, {year: '1939', id: null}];
  assert.ok(h.followDeportHTML(stops).includes('Wien'));
  assert.equal(h.followDeportHTML([{year: '1940', id: 1}]), '');
});
