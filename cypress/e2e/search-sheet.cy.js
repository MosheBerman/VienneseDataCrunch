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
});
