FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/40-suraksha-config.sh /docker-entrypoint.d/40-suraksha-config.sh
COPY index.html support.js config.js i18n.js favicon.svg /usr/share/nginx/html/
COPY i18n /usr/share/nginx/html/i18n
COPY vendor /usr/share/nginx/html/vendor
RUN chmod +x /docker-entrypoint.d/40-suraksha-config.sh && chmod -R a+rX /usr/share/nginx/html
HEALTHCHECK --interval=30s --timeout=5s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
