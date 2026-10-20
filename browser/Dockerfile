# Browser runner: one sandboxed Chromium per attempt, driven by the orchestration worker over
# Playwright's protocol. Pinned to the Playwright version in backend/uv.lock (1.56.0, Chromium
# 141 headless shell, build 1194) so the worker's client and this driver are the same release.
# No application code, credentials or user data are copied into this image.
FROM python:3.12-slim-bookworm

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# The Python package is used only for its bundled driver (Node + playwright-core 1.56.0).
RUN pip install "playwright==1.56.0" \
 && playwright install --with-deps --only-shell chromium \
 && rm -rf /var/lib/apt/lists/* /root/.cache \
 && useradd --uid 10002 --user-group --no-create-home --home-dir /tmp --shell /usr/sbin/nologin browser

COPY launcher.js /opt/runner/launcher.js

ENV DRIVER_PACKAGE=/usr/local/lib/python3.12/site-packages/playwright/driver/package \
    NODE_BIN=/usr/local/lib/python3.12/site-packages/playwright/driver/node \
    HOME=/tmp TMPDIR=/tmp

USER 10002:10002
WORKDIR /tmp
EXPOSE 9330
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
  CMD ["/usr/local/lib/python3.12/site-packages/playwright/driver/node", "-e", "require('http').get('http://127.0.0.1:9330/health', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"]
CMD ["/usr/local/lib/python3.12/site-packages/playwright/driver/node", "/opt/runner/launcher.js"]
