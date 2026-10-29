// Shared helpers for the Lehmann map suite.

// Visit the app with the service worker stubbed out (the app only calls
// navigator.serviceWorker.register(), guarded by a feature check, so a
// resolving stub is enough) and wait for the boot overlay to finish.
// The real worker's cache-first asset handling could otherwise serve
// stale files between test runs.
Cypress.Commands.add('visitApp', () => {
  cy.visit('/', {
    onBeforeLoad(win) {
      const swStub = {
        register: () => Promise.resolve({ scope: '' }),
        getRegistrations: () => Promise.resolve([]),
        getRegistration: () => Promise.resolve(undefined),
        ready: Promise.resolve({}),
        addEventListener: () => {},
        removeEventListener: () => {},
        controller: null,
      };
      try {
        Object.defineProperty(win.navigator, 'serviceWorker',
          { value: swStub, configurable: true });
      } catch (e) {}
    },
  });
  cy.get('#boot', { timeout: 60000 }).should('have.class', 'gone');
});

// Mapbox GL and tile errors are environmental noise for these DOM and
// search-behavior tests; never let them fail a spec.
Cypress.on('uncaught:exception', (err) => {
  const msg = String(err && err.message || err);
  if (/mapbox|webgl|gl context|canvas|tile/i.test(msg)) return false;
  return true;
});
