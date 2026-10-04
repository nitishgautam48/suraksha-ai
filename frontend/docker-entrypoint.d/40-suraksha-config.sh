#!/bin/sh
# Write runtime config for the browser from environment variables (runs before nginx starts).
set -e
cat > /usr/share/nginx/html/config.js <<CFG
window.SURAKSHA_CONFIG = {apiBase: "${API_BASE:-/api}", googleClientId: "${GOOGLE_CLIENT_ID:-}"};
window.__resources = {
  "https://unpkg.com/react@18.3.1/umd/react.production.min.js": "./vendor/react.production.min.js",
  "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js": "./vendor/react-dom.production.min.js"
};
CFG
