FROM node:24-slim

# poppler-utils extracts a PDF's text layer and rasterizes its scanned pages.
ARG COMMIT
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git poppler-utils \
    && git clone https://github.com/jshsakura/mcp-local-vision.git /app \
    && git -C /app checkout "${COMMIT}" \
    && rm -rf /app/.git \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN npm ci --omit=dev

ENTRYPOINT ["node", "/app/src/index.mjs"]
