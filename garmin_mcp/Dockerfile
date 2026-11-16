# Garmin Connect MCP – Home Assistant app
# Debian-based Python image: garminconnect needs curl_cffi, which ships
# glibc wheels for amd64 and arm64.
FROM python:3.12-slim

# Pinned upstream server version (https://github.com/Taxuspt/garmin_mcp).
# Bump deliberately after testing; never track a moving branch.
ARG UPSTREAM_REF=a2ca5fcac34524b83814fe2fcf3d479f8a75983f
ARG BUILD_VERSION=dev
ARG BUILD_ARCH=amd64

ENV APP_VERSION=${BUILD_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY constraints.txt /tmp/constraints.txt

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends nginx git ca-certificates; \
    pip install -c /tmp/constraints.txt \
        "garmin-mcp @ git+https://github.com/Taxuspt/garmin_mcp@${UPSTREAM_REF}" \
        uvicorn starlette python-multipart; \
    apt-get purge -y git; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled /root/.cache /tmp/constraints.txt; \
    python -c "import garmin_mcp, garmin_mcp.tool_annotations, curl_cffi"

# Unprivileged user for the internet-facing MCP server: no login shell and no
# write access to the Home Assistant configuration folder.
RUN useradd --system --no-create-home --home-dir /data/mcp_home --shell /usr/sbin/nologin garmin

COPY rootfs/ /

LABEL \
    io.hass.name="Garmin Connect MCP" \
    io.hass.description="MCP server for Garmin Connect" \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/mw-hbg/ha-apps" \
    org.opencontainers.image.licenses="MIT"

# Health check: the Supervisor restarts the app when the web UI stops answering
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/status.json', timeout=4)" || exit 1

CMD ["python3", "-u", "/app/launcher.py"]
