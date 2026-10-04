// Runtime configuration. In Docker this file is regenerated at container start from environment
// variables (see frontend/docker-entrypoint.d/40-suraksha-config.sh).
window.SURAKSHA_CONFIG = {apiBase: "/api", googleClientId: ""};
// Serve React from this origin instead of a public CDN (privacy, CSP, low bandwidth).
window.__resources = {
  "https://unpkg.com/react@18.3.1/umd/react.production.min.js": "./vendor/react.production.min.js",
  "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js": "./vendor/react-dom.production.min.js"
};
