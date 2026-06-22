FROM docker.io/alpine:3.22

RUN apk add --no-cache gettext pgbouncer

COPY ./compose/production/pgbouncer/entrypoint /entrypoint
COPY ./compose/production/pgbouncer/pgbouncer.ini.template /etc/pgbouncer/pgbouncer.ini.template

RUN chmod +x /entrypoint

ENTRYPOINT ["/entrypoint"]
