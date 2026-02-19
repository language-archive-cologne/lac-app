# syntax=docker/dockerfile:1.7

# define an alias for the specific python version used in this file.
FROM docker.io/python:3.12-slim-trixie@sha256:9e01bf1ae5db7649a236da7be1e94ffbbbdd7a93f867dd0d8d5720d9e1f89fab AS python

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

# Install uv from a pinned image digest
COPY --from=ghcr.io/astral-sh/uv@sha256:4cac394b6b72846f8a85a7a0e577c6d61d4e17fe2ccee65d9451a8b3c9efb4ac /uv /uvx /bin/

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
    # psycopg runtime dependency
    libpq5 \
    wait-for-it \
    # Translations dependencies
    gettext \
    # XML Security tooling for SAML assertions
    xmlsec1 \
    curl

# Create non-root runtime user
RUN groupadd --gid 1000 dev-user \
    && useradd --uid 1000 --gid dev-user --shell /bin/bash --create-home dev-user

# Copy Python packages from build stage - SAME Python base image ensures compatibility
COPY --from=python-build-stage /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-build-stage /usr/local/bin /usr/local/bin

COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint && chmod +x /entrypoint

COPY ./compose/local/django/start /start
RUN sed -i 's/\r$//g' /start && chmod +x /start

# copy application code to WORKDIR
COPY . ${APP_HOME}
RUN chown -R dev-user:dev-user ${APP_HOME}

# Web image target (Django/ASGI)
FROM python-runtime-base AS web-run-stage
USER dev-user
ENTRYPOINT ["/entrypoint"]

# Worker image target (Huey with media tooling)
FROM python-runtime-base AS worker-run-stage
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install --no-install-recommends -y \
    # ffmpeg/ffprobe for media duration detection
    ffmpeg

# Install audiowaveform from upstream .deb (not in Debian repos)
ARG AUDIOWAVEFORM_VERSION=1.10.2
ARG AUDIOWAVEFORM_DEB_SHA256=4208706c6ae5ffb5761dddf8294eaf648c7ba9fb4d6fc6ec9f021d1bb109ea6e
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    curl -fsSL "https://github.com/bbc/audiowaveform/releases/download/${AUDIOWAVEFORM_VERSION}/audiowaveform_${AUDIOWAVEFORM_VERSION}-1-13_amd64.deb" -o /tmp/aw.deb \
    && echo "${AUDIOWAVEFORM_DEB_SHA256}  /tmp/aw.deb" | sha256sum -c - \
    && apt-get update && apt-get install -y --no-install-recommends /tmp/aw.deb \
    && rm /tmp/aw.deb

USER dev-user
ENTRYPOINT ["/entrypoint"]
