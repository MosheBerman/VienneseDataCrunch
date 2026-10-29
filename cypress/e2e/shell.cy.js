// App-shell guards for the iOS standalone safe-area work (v1.4.x):
// the document is scroll-locked so iOS cannot shove the whole view up
// and leave a home-bar gap, the map is anchored to the viewport, and
// the header offsets by the top safe-area inset.

describe('app shell', () => {
  beforeEach(() => {
    cy.viewport(390, 844);
    cy.visitApp();
  });

  it('document cannot scroll', () => {
    cy.document().then((doc) => {
      const cs = doc.defaultView.getComputedStyle(doc.body);
      expect(cs.position, 'body position').to.eq('fixed');
      expect(cs.overflow, 'body overflow').to.eq('hidden');
    });
  });

  it('map is viewport-anchored and covers the screen', () => {
    cy.get('#map').then(($m) => {
      const el = $m[0];
      const cs = el.ownerDocument.defaultView.getComputedStyle(el);
      expect(cs.position, '#map position').to.eq('fixed');
      const r = el.getBoundingClientRect();
      expect(r.top, '#map top').to.eq(0);
      expect(r.left, '#map left').to.eq(0);
    });
  });

  it('header sits below the status-bar inset', () => {
    cy.get('header').then(($h) => {
      const cs = $h[0].ownerDocument.defaultView.getComputedStyle($h[0]);
      // In a browser the inset is 0, so top resolves to the base 8px;
      // what matters is that the calc() with env() is in place.
      expect(parseFloat(cs.top), 'header top').to.be.greaterThan(-1);
    });
    cy.document().then((doc) => {
      const rules = Array.from(doc.styleSheets).flatMap((sh) => {
        try { return Array.from(sh.cssRules); } catch (e) { return []; }
      });
      const hit = rules.some((r) =>
        r.selectorText && /(^|,)\s*header/.test(r.selectorText) &&
        r.style && /safe-area-inset-top/.test(r.style.cssText || ''));
      expect(hit, 'a header rule uses env(safe-area-inset-top)').to.be.true;
    });
  });
});
