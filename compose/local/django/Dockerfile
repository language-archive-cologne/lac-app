# syntax=docker/dockerfile:1.7

# define an alias for the specific python version used in this file.
FROM docker.io/python:3.12.8-slim-bookworm AS python

# Python build stage
FROM python AS python-build-stage
ARG BUILD_ENVIRONMENT=local

# Install apt packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install --no-install-recommends -y \
    # dependencies for building Python packages
    build-essential \
    # psycopg dependencies
    libpq-dev

# Install uv using the more reliable COPY method from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Requirements are installed here to ensure they will be cached.
COPY ./requirements /requirements

# Install Python dependencies with cache mounting
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r /requirements/${BUILD_ENVIRONMENT}.txt

# Shared Python runtime stage (used by both web and worker targets)
FROM python AS python-runtime-base
ARG BUILD_ENVIRONMENT=local
ARG APP_HOME=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV BUILD_ENV=${BUILD_ENVIRONMENT}
WORKDIR ${APP_HOME}

# Install common runtime dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install --no-install-recommends -y \
    # devcontainer dependencies and utils
    sudo git bash-completion nano ssh \
    # psycopg dependencies
    libpq-dev \
    wait-for-it \
    # Translations dependencies
    gettext \
    # XML Security tooling for SAML assertions
    xmlsec1 \
    curl

# Create devcontainer user and add it to sudoers
RUN groupadd --gid 1000 dev-user \
    && useradd --uid 1000 --gid dev-user --shell /bin/bash --create-home dev-user \
    && echo dev-user ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/dev-user \
    && chmod 0440 /etc/sudoers.d/dev-user

# Copy Python packages from build stage - SAME Python base image ensures compatibility
COPY --from=python-build-stage /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-build-stage /usr/local/bin /usr/local/bin

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint && chmod +x /entrypoint

COPY ./compose/local/django/start /start
RUN sed -i 's/\r$//g' /start && chmod +x /start

# copy application code to WORKDIR
COPY . ${APP_HOME}

# Web image target (Django/ASGI)
FROM python-runtime-base AS web-run-stage
ENTRYPOINT ["/entrypoint"]

# Worker image target (Huey with media + backup tooling)
FROM python-runtime-base AS worker-run-stage
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install --no-install-recommends -y \
    # Required to run docker compose backup command from Huey tasks
    docker.io \
    docker-compose \
    # ffmpeg/ffprobe for media duration detection
    ffmpeg

# Install audiowaveform from upstream .deb (not in Debian repos)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    curl -fsSL https://github.com/bbc/audiowaveform/releases/download/1.10.2/audiowaveform_1.10.2-1-12_amd64.deb -o /tmp/aw.deb \
    && apt-get update && apt-get install -y --no-install-recommends /tmp/aw.deb \
    && rm /tmp/aw.deb

ENTRYPOINT ["/entrypoint"]
