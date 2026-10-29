// Mobile search sheet behavior, including the 2026-10-29 regression:
// when the results sheet opened, the search dock was moved into the
// sheet in the DOM, and moving the focused input made iOS drop the
// keyboard mid-typing. The move now carries focus and caret across.

describe('mobile search sheet', () => {
  beforeEach(() => {
    cy.viewport(390, 844);
    cy.visitApp();
  });

  it('typing keeps focus when the results sheet opens', () => {
    cy.get('#q').type('Willner', { delay: 60 });
    cy.get('#resHead', { timeout: 30000 }).should('exist');
    cy.get('#results').should('be.visible');
    // The dock (with the input) now lives inside the sheet...
    cy.get('#results #searchDock').should('exist');
    // ...and the input kept focus and its text.
    cy.focused().should('have.id', 'q');
    cy.get('#q').should('have.value', 'Willner');
    // Typing still lands after the move.
    cy.get('#q').type('s');
    cy.get('#q').should('have.value', 'Willners');
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
    // Drag the header up: covers the map at the full detent (97%).
    cy.get('#resHead').trigger('pointerdown', { clientX: 200, clientY: 600 });
    cy.get('#resHead').trigger('pointermove', { clientX: 200, clientY: 180 });
    cy.get('#resHead').trigger('pointerup', { clientX: 200, clientY: 180 });
    height().should('be.greaterThan', 780);
    // Drag it back down: the collapsed detent (~18%) keeps the dock
    // and header visible instead of dismissing the sheet.
    cy.get('#resHead').trigger('pointerdown', { clientX: 200, clientY: 150 });
    cy.get('#resHead').trigger('pointermove', { clientX: 200, clientY: 800 });
    cy.get('#resHead').trigger('pointerup', { clientX: 200, clientY: 800 });
    height().should('be.within', 110, 210);
    cy.get('#results').should('be.visible');
    cy.get('#results #searchDock').should('exist');
  });

  it('detail shows an expand button on the scan excerpt and no play button', () => {
    cy.get('#fwPlay').should('not.exist');
    cy.get('#q').type('Bermann');
    cy.get('#results .rrow', { timeout: 30000 }).first().click();
    cy.get('#pointSheet .rowsnip-expand', { timeout: 30000 })
      .should('exist')
      .and('have.attr', 'href')
      .and('match', /digital\.wienbibliothek\.at\/image\/view\//);
  });
});
