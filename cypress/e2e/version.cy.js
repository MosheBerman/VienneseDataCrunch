// Version display consistency, including the 2026-10-29 catch: the
// launch screen (bottom-right, #bootVersion) and the About sheet's
// source line must show the same release. They drifted once (the About
// sheet's static line sat at v1.0.0 through three releases).

describe('version display', () => {
  beforeEach(() => {
    cy.viewport(1280, 800);
    cy.visitApp();
  });

  it('launch screen and About sheet agree on the version', () => {
    cy.get('#bootVersion').invoke('text').then((boot) => {
      const v = boot.trim();
      expect(v, 'boot version format').to.match(/^v\d+\.\d+\.\d+$/);
      cy.get('#infoBtn').click();
      cy.get('#aboutOverlay').should('have.class', 'open');
      cy.get('#aboutBox p[data-i18n-html="sourceLine"] code')
        .invoke('text')
        .should('eq', v);
    });
  });
});
