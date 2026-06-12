# syntax=docker/dockerfile:1
#
# Dockerfile for the NX Witness MCP server.
#
# Mental model: this file is a *recipe*. Each instruction below is a step that
# Docker runs top-to-bottom to bake an *image* (a sealed, shippable snapshot of
# the app + its dependencies). You later run that image to get a *container*
# (one live instance). Secrets are NOT baked in here — they are handed to the
# container at runtime (via Infisical / env vars), like adding salt at the table
# instead of the factory.

# ---- Base image -----------------------------------------------------------
# Start from an official, slim Python image. "slim" = Debian with Python and
# little else, so the image stays small. 3.12 comfortably satisfies the app's
# "Python 3.9+" requirement.
FROM python:3.12-slim

# ---- Build-time environment ----------------------------------------------
# PYTHONDONTWRITEBYTECODE: don't litter the image with .pyc files.
# PYTHONUNBUFFERED: send stdout/stderr straight to the logs (no buffering),
#   so `docker logs` shows output immediately — important for a server.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- Working directory ----------------------------------------------------
# All following paths are relative to /app. Docker creates it if missing.
WORKDIR /app

# ---- Dependencies (cached layer) -----------------------------------------
# Copy ONLY requirements.txt first, then install. Docker caches each layer; as
# long as requirements.txt doesn't change, rebuilds skip re-installing deps even
# when the app code changes. --no-cache-dir keeps pip's download cache out of
# the image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Application code -----------------------------------------------------
# Copy only the three files the server actually needs at runtime. The large
# reference JSONs and the secret nx_systems.json are excluded via .dockerignore.
COPY server.py nx_client.py middleware.py ./

# ---- Run as a non-root user ----------------------------------------------
# Security posture: never run the server as root inside the container. Create an
# unprivileged user and hand it ownership of /app.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# ---- Runtime configuration -----------------------------------------------
# Defaults read by server.py's __main__ block. NX_HOST/NX_USER/NX_PASS are
# intentionally left UNSET here — they are injected at runtime by Infisical so
# no credentials ever live in the image.
ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

# Document the port the server listens on (informational; publish it with
# `docker run -p` or the compose file).
EXPOSE 8000

# ---- Healthcheck ----------------------------------------------------------
# Is the server actually accepting connections? The slim image has no curl, so
# we use Python's stdlib to open a TCP socket to MCP_PORT. Exit 0 = healthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket,os; socket.create_connection(('127.0.0.1', int(os.environ.get('MCP_PORT','8000'))), 3)" || exit 1

# ---- Start command --------------------------------------------------------
# What runs when the container starts. server.py spins up uvicorn on
# MCP_HOST:MCP_PORT and serves MCP over Streamable HTTP.
CMD ["python", "server.py"]
