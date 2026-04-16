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
# bust the pip cache.
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy the rest of the application.
COPY . .

# Drop to an unprivileged user. The /data mount point (Railway volume) must
# be writable — it's created/owned by appuser so `flask db-init` can create
# portal.db on first boot. Railway bind-mounts over this at runtime.
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} (set by Railway) is expanded. Railway's startCommand
# in railway.toml overrides this CMD with `flask db-init && gunicorn ...`.
CMD gunicorn "app:create_app()" --bind "0.0.0.0:${PORT}" --workers 2 --access-logfile - --error-logfile -
