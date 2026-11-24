# syntax=docker/dockerfile:1
#
# Multi-arch container for JerumedNexus Gateway.
#
# Build:
#   docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 \
#                       -t ghcr.io/jerumed-nexus/jerumednexus-gateway:1.1.0 \
#                       --push .
#
# Run (single-node):
#   docker compose up -d          # uses docker-compose.yml
#

FROM python:3.12-slim-bookworm AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libffi-dev libssl-dev \
        ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --system --gid 900 loc200 \
 && useradd  --system --uid 900 --gid loc200 --home /app --shell /usr/sbin/nologin loc200

WORKDIR /app

# Deps first for cache
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r requirements.txt

# App
COPY --chown=loc200:loc200 main.py ./
COPY --chown=loc200:loc200 src/    ./src/
COPY --chown=loc200:loc200 config/ ./config/
COPY --chown=loc200:loc200 webui/  ./webui/
COPY --chown=loc200:loc200 tools/  ./tools/

# Runtime state
RUN mkdir -p /app/logs /app/state \
 && chown -R loc200:loc200 /app/logs /app/state

USER loc200

# Volumes for config + logs + state
VOLUME ["/app/config", "/app/logs", "/app/state"]

# Web UI + LOC-200 HTTP ingestion
EXPOSE 8080 5003

# Tini gives us proper PID 1 signal handling (SIGTERM/SIGINT/SIGHUP)
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default command runs the gateway; override to run the webui:
#   command: python -m flask --app webui.app run --host=0.0.0.0 --port=8080
CMD ["python", "main.py"]
