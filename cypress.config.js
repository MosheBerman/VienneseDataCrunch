const { defineConfig } = require('cypress');

// The suite runs against the live deployment: the Mapbox token in
// index.html is restricted to the production origin, so the map (and
// therefore the boot sequence) never finishes on localhost. Override
// with CYPRESS_baseUrl to repoint, e.g. at a preview deploy.
module.exports = defineConfig({
  e2e: {
    baseUrl: 'https://mosheberman.github.io/VienneseDataCrunch/',
    specPattern: 'cypress/e2e/**/*.cy.js',
    supportFile: 'cypress/support/e2e.js',
    video: false,
    screenshotOnRunFailure: true,
    defaultCommandTimeout: 20000,
    pageLoadTimeout: 180000,
  },
});
