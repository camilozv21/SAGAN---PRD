# syntax=docker/dockerfile:1.6
# AW Client Report Portal — single image used locally and on Railway.
# Base: python:3.11-slim (Debian Bookworm) + WeasyPrint native deps.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# WeasyPrint needs pango/cairo/gdk-pixbuf/fontconfig at runtime. The -dev
# packages are only needed during wheel builds (cffi, cairocffi); we pull
# them into a builder stage and drop them from the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps in their own layer so application code edits don't
# bust the pip cache. We deliberately avoid `--mount=type=cache` because
# Railway's BuildKit config rejects anonymous cache mounts (requires an
# explicit id=) — the layer cache is enough.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the rest of the application.
COPY . .

# Run as root. Railway's persistent volume at /data was created by the prior
# Nixpacks deploy as root:root; an unprivileged user can't write portal.db
# to it, which makes `flask db-init` fail and the healthcheck never pass.
# This is an internal tool for 3 users behind Railway auth — root is fine.
RUN mkdir -p /data

ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} (set by Railway) is expanded. Railway's startCommand
# in railway.toml overrides this CMD with `flask db-init && gunicorn ...`.
CMD gunicorn "app:create_app()" --bind "0.0.0.0:${PORT}" --workers 2 --access-logfile - --error-logfile -
