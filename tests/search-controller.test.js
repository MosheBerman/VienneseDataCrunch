// Sandbox tests for the search firing controller.
//
// We care about FIRING here, not results: when a search starts, with
// what text, and whether a superseded run stays current. The controller
// is extracted verbatim from index.html (between the SEARCH_CONTROLLER
// markers) so these tests run the production code, not a copy, in Node
// with fake timers: no browser, no map, no 30 MB index, no network.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const m = html.match(/\/\/ SEARCH_CONTROLLER_BEGIN([\s\S]*?)\/\/ SEARCH_CONTROLLER_END/);
assert.ok(m, 'controller markers found in index.html');
const createSearchController = new Function(m[1] + '; return createSearchController;')();

function harness(){
  let now = 0, nextId = 1;
  const timers = new Map();
  let seq = 0;
  const h = {
    text: '',
    calls: [],      // tokens handed to runSearch, in order
    emptyCalls: 0,
    setText(t){ h.text = t; },
    advance(ms){
      const until = now + ms;
      for (;;){
        let due = null;
        for (const [id, t] of timers) if (t.at <= until && (!due || t.at < due.t.at)) due = {id, t};
        if (!due) break;
        timers.delete(due.id); now = due.t.at; due.t.fn();
      }
      now = until;
    }
  };
  h.ctl = createSearchController({
    readText: () => h.text,
    runSearch: token => h.calls.push(token),
    onEmpty: () => { h.emptyCalls++; },
    debounceMs: 350, minLive: 3, minCommit: 2,
    setTimeoutFn: (fn, ms) => { const id = nextId++; timers.set(id, {fn, at: now + ms}); return id; },
    clearTimeoutFn: id => timers.delete(id),
    bumpSeq: () => ++seq,
    getSeq: () => seq
  });
  // Simulate one keystroke landing in the box, then the input event.
  h.type = t => { h.text = t; h.ctl.inputChanged(); };
  return h;
}

test('no fire at threshold - 1 ms of quiet, exactly one once the pause passes the threshold', () => {
  const h = harness();
  h.type('berm');
  h.advance(349);
  assert.equal(h.calls.length, 0);
  h.advance(2); // quiet is now 351 ms: past the 350 ms threshold
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].text, 'berm');
  assert.equal(h.calls[0].commit, false);
});

test('each keystroke pushes the pause out: one fire, with the final text', () => {
  const h = harness();
  h.type('ber');
  h.advance(300);
  h.type('berm');
  h.advance(300);
  h.type('berma');
  h.advance(349);
  assert.equal(h.calls.length, 0);
  h.advance(2);
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].text, 'berma');
});

test('long pauses (1 s, 5 s) still produce exactly one fire per quiet period', () => {
  const h = harness();
  h.type('willner');
  h.advance(1000);
  assert.equal(h.calls.length, 1);
  h.type('willners');
  h.advance(5000);
  assert.equal(h.calls.length, 2);
  assert.equal(h.calls[1].text, 'willners');
});

test('below the live minimum nothing fires and results dismiss at once', () => {
  const h = harness();
  h.type('be');
  assert.equal(h.calls.length, 0);
  assert.equal(h.emptyCalls, 1);
  assert.equal(h.ctl.pending(), false);
  h.advance(5000);
  assert.equal(h.calls.length, 0);
});

test('emptying the box (backspace to empty / select-all + delete) cancels and invalidates in-flight work', () => {
  const h = harness();
  h.type('bermann');
  h.advance(351);
  assert.equal(h.calls.length, 1);
  const inFlight = h.calls[0];
  assert.equal(inFlight.isCurrent(), true);
  h.type('');
  assert.equal(h.emptyCalls, 1);
  assert.equal(inFlight.isCurrent(), false, 'in-flight run is stale after the box empties');
  h.advance(5000);
  assert.equal(h.calls.length, 1, 'no further fire from the emptied box');
});

test('latest wins: typing on makes a running token stale before the next fire', () => {
  const h = harness();
  h.type('berm');
  h.advance(351);
  const first = h.calls[0];
  assert.equal(first.isCurrent(), true);
  h.type('berma'); // debounce pending, no new fire yet
  assert.equal(first.isCurrent(), false, 'text changed under the running search');
  h.advance(351);
  assert.equal(h.calls.length, 2);
  assert.equal(h.calls[1].text, 'berma');
  assert.equal(h.calls[1].isCurrent(), true);
  assert.equal(first.isCurrent(), false);
});

test('Enter commits a 2-char query that live search holds back', () => {
  const h = harness();
  h.setText('be');
  h.ctl.commit();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].text, 'be');
  assert.equal(h.calls[0].commit, true);
});

test('Enter does not commit a 1-char query', () => {
  const h = harness();
  h.setText('b');
  h.ctl.commit();
  assert.equal(h.calls.length, 0);
});

test('cancel() drops a pending fire and invalidates a running token', () => {
  const h = harness();
  h.type('bermann');
  h.ctl.cancel();
  h.advance(5000);
  assert.equal(h.calls.length, 0);
  h.type('bermann');
  h.advance(351);
  const tok = h.calls[0];
  h.ctl.cancel();
  assert.equal(tok.isCurrent(), false);
});

test('runLive fires immediately with the current text (year-switch re-run)', () => {
  const h = harness();
  h.setText('bermann');
  h.ctl.runLive();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].text, 'bermann');
  assert.equal(h.calls[0].commit, false);
});

test('suspend() invalidates an in-flight run but not a completed one', () => {
  const h = harness();
  h.type('bermann');
  h.advance(351);
  const done = h.calls[0];
  h.ctl.finished(done); // executor reports the render completed
  h.ctl.suspend();      // user minimizes to the pill
  assert.equal(done.isCurrent(), true,
    'completed result set keeps its sequence (chips/pager still work from the pill)');
  h.type('bermann josef');
  h.advance(351);
  const flying = h.calls[1];
  assert.equal(flying.isCurrent(), true);
  h.ctl.suspend();      // minimize while this one is still running
  assert.equal(flying.isCurrent(), false, 'in-flight run cannot reopen the sheet');
});

test('suspend() drops a pending fire', () => {
  const h = harness();
  h.type('bermann');
  h.ctl.suspend();
  h.advance(5000);
  assert.equal(h.calls.length, 0);
});
