// Mobile search sheet behavior. History: 2026-10-29, opening the sheet
// moved the search dock into it in the DOM and iOS dropped the keyboard
// mid-typing; focus/caret were carried across the move as a fix.
// 2026-11-11 (Daniella regression): a second search firing while the
// index loaded wiped the sheet with innerHTML and destroyed the dock
// and input entirely. The dock now NEVER moves: it stays fixed at the
// bottom, the sheet leaves room for it, and search operates on the
// input's text only. These tests assert the input element is the same
// DOM node before and after a search, with its text and focus intact.

describe('mobile search sheet', () => {
  beforeEach(() => {
    cy.viewport(390, 844);
    cy.visitApp();
  });

  it('typing keeps focus when the results sheet opens', () => {
    let qNode;
    cy.get('#q').then(($el) => { qNode = $el[0]; });
    cy.get('#q').type('Willner', { delay: 60 });
    cy.get('#resHead', { timeout: 30000 }).should('exist');
    cy.get('#results').should('be.visible');
    // The dock did not move into the sheet, and the input is untouched.
    cy.get('#results #searchDock').should('not.exist');
    cy.get('header #searchDock').should('exist');
    cy.get('#q').then(($el) => { expect($el[0], 'same input element').to.equal(qNode); });
    cy.focused().should('have.id', 'q');
    cy.get('#q').should('have.value', 'Willner');
    // Typing still lands, at the end, after the sheet opened.
    cy.get('#q').type('s');
    cy.get('#q').should('have.value', 'Willners');
  });

  it('slow typing while the index loads keeps the box (Daniella regression)', () => {
    // Hold the index response open so several searches fire while the
    // first is still loading: the exact interleaving that destroyed
    // the search box. 600 ms per keystroke is a slow, real typist.
    cy.intercept('**/search.idx.json', (req) => {
      req.on('response', (res) => { res.setDelay(6000); });
    });
    let qNode;
    cy.get('#q').then(($el) => { qNode = $el[0]; });
    cy.get('#q').type('Ber', { delay: 600 });
    cy.get('#q').type('mann', { delay: 600 });
    cy.get('#resHead', { timeout: 60000 }).should('exist');
    cy.get('#q').should('have.value', 'Bermann');
    cy.focused().should('have.id', 'q');
    cy.get('#q').then(($el) => { expect($el[0], 'same input element').to.equal(qNode); });
    cy.get('#results .rrow b', { timeout: 30000 }).should(($bs) => {
      const names = Array.from($bs, (b) => b.textContent.trim().toLowerCase());
      expect(names, 'results are for the final text').to.include('bermann');
    });
  });

  it('clearing the query dismisses the results', () => {
    cy.get('#q').type('Bermann');
    cy.get('#resHead', { timeout: 30000 }).should('exist');
    cy.get('#qClear').click();
    cy.get('#resHead').should('not.exist');
    cy.get('#results').should('not.be.visible');
  });

  it('sheet drags up to full height and down to the collapsed detent', () => {
    cy.get('#q').type('Bermann');
    cy.get('#resHead', { timeout: 30000 }).should('exist');
    const height = () => cy.get('#results').then(($el) => $el[0].getBoundingClientRect().height);
    // Opens at the half detent (~52% of 844).
    height().should('be.within', 400, 480);
    // Drag the header up: the top detent (87%; the sheet's bottom sits
    // above the fixed search dock, so it cannot cover the full screen).
    cy.get('#resHead').trigger('pointerdown', { clientX: 200, clientY: 600 });
    cy.get('#resHead').trigger('pointermove', { clientX: 200, clientY: 180 });
    cy.get('#resHead').trigger('pointerup', { clientX: 200, clientY: 180 });
    height().should('be.greaterThan', 700);
    // Drag it back down: the collapsed detent (~18%) keeps the header
    // visible instead of dismissing the sheet.
    cy.get('#resHead').trigger('pointerdown', { clientX: 200, clientY: 150 });
    cy.get('#resHead').trigger('pointermove', { clientX: 200, clientY: 800 });
    cy.get('#resHead').trigger('pointerup', { clientX: 200, clientY: 800 });
    height().should('be.within', 110, 210);
    cy.get('#results').should('be.visible');
    // Throughout, the dock stayed at the bottom of the screen, outside
    // the sheet, where it always lives now.
    cy.get('#results #searchDock').should('not.exist');
    cy.get('#searchDock').should('exist');
  });

  it('detail shows an expand button on the scan excerpt, and the follow play button exists', () => {
    cy.get('#fwPlay').should('exist');
    cy.get('#q').type('Bermann');
    cy.get('#results .rrow', { timeout: 30000 }).first().click();
    cy.get('#pointSheet .rowsnip-expand', { timeout: 30000 })
      .should('exist')
      .and('have.attr', 'href')
      .and('match', /digital\.wienbibliothek\.at\/image\/view\//);
  });

  it('detail carries its own Play button for the year-by-year animation', () => {
    // Regression (2026-11-04): the only Play button lived in the floating
    // follow panel, which the pushed mobile detail never opens, so the
    // animation was unreachable on a phone.
    cy.get('#q').type('Bermann');
    cy.get('#results .rrow', { timeout: 30000 }).first().click();
    cy.get('#pointSheet .fw-play-btn', { timeout: 30000 }).should('be.visible');
    cy.get('#pointSheet .fw-play-btn').click();
    // Playing hands off to the follow panel and closes the sheet so the
    // map (and the travelling dot) is visible.
    cy.get('#followPanel', { timeout: 30000 }).should('be.visible');
    cy.get('#pointSheet').should('not.be.visible');
    cy.get('#fwPlay').should('be.visible');
  });
});
