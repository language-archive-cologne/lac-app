
# define an alias for the specific python version used in this file.
FROM docker.io/python:3.12-slim-trixie@sha256:9e01bf1ae5db7649a236da7be1e94ffbbbdd7a93f867dd0d8d5720d9e1f89fab AS python

# Python build stage
FROM python AS python-build-stage

ARG BUILD_ENVIRONMENT=production

# Make apt resilient in bridged networks (DNS/IPv6 hiccups are common in Docker builds).
RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAcquire::ForceIPv4 "true";\n' > /etc/apt/apt.conf.d/99-network-retries

# Install apt packages
RUN apt-get update && apt-get install --no-install-recommends -y \
  # dependencies for building Python packages
  build-essential \
  # psycopg dependencies
  libpq-dev


# Requirements are installed here to ensure they will be cached.
COPY ./requirements .

# Create Python Dependency and Sub-Dependency Wheels.
RUN pip wheel --wheel-dir /usr/src/app/wheels  \
  -r ${BUILD_ENVIRONMENT}.txt


# Python 'run' stage
FROM python AS python-run-stage

ARG BUILD_ENVIRONMENT=production
ARG APP_HOME=/app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV BUILD_ENV=${BUILD_ENVIRONMENT}

WORKDIR ${APP_HOME}

# Keep apt behavior robust in the runtime stage too.
RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAcquire::ForceIPv4 "true";\n' > /etc/apt/apt.conf.d/99-network-retries

RUN addgroup --system django \
  && adduser --system --ingroup django django


# Install required system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
  # psycopg runtime dependency
  libpq5 \
  # XML Security tooling for SAML assertions
  xmlsec1 \
  # Translations dependencies
  gettext \
  # entrypoint
  wait-for-it \
  # ffmpeg/ffprobe for media duration detection
  ffmpeg \
  curl \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

# Install audiowaveform from upstream .deb (not in Debian repos)
ARG AUDIOWAVEFORM_VERSION=1.10.2
ARG AUDIOWAVEFORM_DEB_SHA256=4208706c6ae5ffb5761dddf8294eaf648c7ba9fb4d6fc6ec9f021d1bb109ea6e
RUN curl -fsSL "https://github.com/bbc/audiowaveform/releases/download/${AUDIOWAVEFORM_VERSION}/audiowaveform_${AUDIOWAVEFORM_VERSION}-1-13_amd64.deb" -o /tmp/aw.deb \
  && echo "${AUDIOWAVEFORM_DEB_SHA256}  /tmp/aw.deb" | sha256sum -c - \
  && apt-get update && apt-get install -y --no-install-recommends /tmp/aw.deb \
  && rm /tmp/aw.deb \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# All absolute dir copies ignore workdir instruction. All relative dir copies are wrt to the workdir instruction
# copy python dependency wheels from python-build-stage
COPY --from=python-build-stage /usr/src/app/wheels  /wheels/

# use wheels to install python dependencies
RUN pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* \
  && rm -rf /wheels/


COPY --chown=django:django ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint
RUN chmod +x /entrypoint


COPY --chown=django:django ./compose/production/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start


# copy application code to WORKDIR
COPY --chown=django:django . ${APP_HOME}

# make django owner of the WORKDIR directory as well.
RUN chown -R django:django ${APP_HOME}

USER django

RUN DATABASE_URL="" \
  DJANGO_SETTINGS_MODULE="config.settings.test" \
  python manage.py compilemessages

ENTRYPOINT ["/entrypoint"]
