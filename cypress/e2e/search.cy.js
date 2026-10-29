// Search correctness, including the 2026-10-29 'Willner' regression:
// an unanchored term (no exact key in the year index) opened the
// edit-distance-2 net and returned ~7,500 junk hits (Kellner the
// occupation, Wiedner, ...) sorted A-Z, so the results looked like an
// unfiltered list. Unanchored terms now search at distance 1.

function headCount() {
  return cy.get('#resHead span').first().invoke('text')
    .then((t) => parseInt(t.replace(/[^0-9]/g, ''), 10));
}

describe('search', () => {
  beforeEach(() => {
    cy.viewport(1280, 800);
    cy.visitApp();
  });

  it('unanchored term (Willner, 1938) returns close variants, not a flood', () => {
    cy.get('#q').type('Willner');
    cy.get('#results').should('be.visible');
    cy.get('#resHead', { timeout: 30000 }).should('exist');
    headCount().then((n) => {
      expect(n, 'match count').to.be.greaterThan(50);
      expect(n, 'match count (was 7,508 before the fix)').to.be.lessThan(1500);
    });
    // The flood signature was field pollution: the occupation field
    // alone carried 3,944 of the 7,508 junk hits (Kellner). Post-fix
    // the hits are almost all names (live at fix time: Names 425,
    // Streets 0, Occupations 1), so check the filter-chip counts.
    const chipCount = (label) => cy.get('#results .chip', { timeout: 30000 })
      .filter((i, el) => el.textContent.trim().startsWith(label))
      .first().invoke('text')
      .then((t) => parseInt((t.match(/\(([\d,]+)\)/) || [])[1].replace(/,/g, ''), 10));
    chipCount('Names').then((n) => {
      expect(n, 'name-field hits').to.be.greaterThan(300);
    });
    chipCount('Occupations').then((n) => {
      expect(n, 'occupation-field hits').to.be.lessThan(25);
    });
  });

  it('anchored term (Bermann) surfaces Bermann records on page one', () => {
    cy.get('#q').type('Bermann');
    cy.get('#resHead', { timeout: 30000 }).should('exist');
    headCount().then((n) => {
      expect(n, 'match count').to.be.greaterThan(100);
    });
    // Exact matches sort first (surname order within the tier). The
    // very first row can be an exact given-name match (Bermann
    // Benzion), so assert Bermann surnames appear on the first page.
    // Rows append in chunks after the shards load, so use a
    // retrying assertion over the live row set rather than a
    // one-shot snapshot.
    cy.get('#results .rrow b', { timeout: 30000 }).should(($bs) => {
      const names = Array.from($bs, (b) => b.textContent.trim().toLowerCase());
      expect(names, 'first page surnames').to.include('bermann');
    });
  });

  it('short query (under 2 chars) shows no results', () => {
    cy.get('#q').type('W');
    cy.wait(600);
    cy.get('#resHead').should('not.exist');
  });
});
