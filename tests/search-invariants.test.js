// Static invariants for the search UI, the rules that the Daniella bug
// violated. These read index.html as text: cheap, and they fail the
// moment a future change reintroduces a forbidden pattern.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');

test('the search dock is never moved, and caret is never managed', () => {
  assert.ok(!html.includes('prepend(dock'), 'dock is not reparented into the sheet');
  assert.ok(!html.includes('in-sheet'), 'no in-sheet dock mode remains');
  assert.ok(!html.includes('setSelectionRange'), 'no caret capture/restore');
  assert.ok(!html.includes('function dockToHeader'), 'dockToHeader is gone: the dock never leaves home');
});

test('the results sheet is never cleared with innerHTML', () => {
  assert.ok(!html.includes("box.innerHTML = '<div class=\"r-load\""), 'old spinner wipe is gone');
  // Every results-clearing path goes through the dock-safe helper.
  assert.ok(html.includes('function clearResultsContent(box)'), 'dock-safe clear helper exists');
});

test('only clearSearch() may empty the search box', () => {
  const assign = /\$\('q'\)\.value = ''/g;
  assert.equal((html.match(assign) || []).length, 0, 'no direct q.value clear (switchYear included)');
  const body = html.match(/function clearSearch\(\)\{([\s\S]*?)\n\}/);
  assert.ok(body, 'clearSearch exists');
  assert.ok(body[1].includes("q.value = '';"), 'clearSearch is the one place that empties the box');
  const all = html.match(/q\.value = '';/g) || [];
  assert.equal(all.length, 1, 'exactly one q.value clear in the file');
});

test('firing constants are the agreed ones', () => {
  assert.ok(html.includes('const SEARCH_DEBOUNCE_MS = 350;'));
  assert.ok(html.includes('const SEARCH_MIN_LIVE = 3;'));
  assert.ok(html.includes('const SEARCH_MIN_COMMIT = 2;'));
});
