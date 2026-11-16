# Garmin Connect MCP – Home Assistant add-on
# Debian-based Python image: garminconnect needs curl_cffi, which ships
# glibc wheels for amd64 and arm64.
FROM python:3.12-slim

# Pinned upstream server version (https://github.com/Taxuspt/garmin_mcp).
# Bump deliberately after testing; never track a moving branch.
ARG UPSTREAM_REF=a2ca5fcac34524b83814fe2fcf3d479f8a75983f
ARG BUILD_VERSION=dev
ARG BUILD_ARCH=amd64

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends nginx git ca-certificates; \
    pip install \
        "garmin-mcp @ git+https://github.com/Taxuspt/garmin_mcp@${UPSTREAM_REF}" \
        "uvicorn>=0.30" "starlette>=0.40" "python-multipart>=0.0.9"; \
    apt-get purge -y git; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled /root/.cache; \
    python -c "import garmin_mcp, garmin_mcp.tool_annotations, curl_cffi"

COPY rootfs/ /

LABEL \
    io.hass.name="Garmin Connect MCP" \
    io.hass.description="MCP server for Garmin Connect" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/mw-hbg/ha-garmin-mcp" \
    org.opencontainers.image.licenses="MIT"

CMD ["python3", "-u", "/app/launcher.py"]
