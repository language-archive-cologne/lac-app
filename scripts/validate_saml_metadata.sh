#!/usr/bin/env bash
# Generate LACOS SP metadata and validate it with the same CLARIN tooling used
# by clarin-eric/SPF-SPs-metadata pull request checks.
#
# Requires: docker and docker compose. Java/Ant/xmllint are installed only inside
# a disposable validator container, not in the LACOS application image.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPOSE_FILE_PATH="${SAML_PREFLIGHT_COMPOSE_FILE:-docker-compose.local.yml}"
DJANGO_SERVICE="${SAML_PREFLIGHT_DJANGO_SERVICE:-django}"
DJANGO_SETTINGS="${SAML_PREFLIGHT_DJANGO_SETTINGS:-config.settings.test}"
BASE_URL="${SAML_PREFLIGHT_BASE_URL:-https://lacos.uni-koeln.de}"
BASE_URL="${BASE_URL%/}"
HOST_FROM_BASE="${BASE_URL#*://}"
HOST_FROM_BASE="${HOST_FROM_BASE%%/*}"
HOST="${SAML_PREFLIGHT_HOST:-${HOST_FROM_BASE}}"
WORK_DIR="${SAML_PREFLIGHT_WORK_DIR:-${REPO_ROOT}/.tmp/saml-preflight}"
TOOL_IMAGE="${SAML_PREFLIGHT_TOOL_IMAGE:-debian:bookworm-slim}"
FAIL_ON_QA_WARNINGS="${SAML_PREFLIGHT_FAIL_ON_QA_WARNINGS:-1}"
KEEP_WORK_DIR="${SAML_PREFLIGHT_KEEP_WORK_DIR:-0}"
DOCKER_DNS_ARGS=()
SEEN_DNS_SERVERS=" "

APP_WORK_DIR="/app/.tmp/saml-preflight"
METADATA_FILE="${WORK_DIR}/metadata.xml"
APP_METADATA_FILE="${APP_WORK_DIR}/metadata.xml"
APP_GENERATOR="${APP_WORK_DIR}/generate_saml_metadata.py"
APP_KEY_FILE="${APP_WORK_DIR}/sp-key.pem"
APP_CERT_FILE="${APP_WORK_DIR}/sp-cert.pem"

log() {
  printf '[saml-preflight] %s\n' "$*"
}

usage() {
  cat <<'EOF'
Usage: scripts/validate_saml_metadata.sh

Generates LACOS SP metadata and validates it with CLARIN's pull-request tools:
  - xmlsectool SAML schema validation
  - CLARIN certificate key-size and expiry check
  - CLARIN Schematron metadata QA

Java, Ant, xmllint, and CLARIN tools run only inside a disposable Docker
validator container. They are not installed into the LACOS app image.

Useful environment variables:
  SAML_PREFLIGHT_BASE_URL=https://lacos.uni-koeln.de
  SAML_PREFLIGHT_SP_KEY_FILE=/host/path/sp-key.pem
  SAML_PREFLIGHT_SP_CERT_FILE=/host/path/sp-cert.pem
  SAML_PREFLIGHT_FAIL_ON_QA_WARNINGS=0
  SAML_PREFLIGHT_KEEP_WORK_DIR=1
  SAML_PREFLIGHT_DOCKER_DNS=134.95.127.3,134.95.127.4

If no key/cert pair is supplied, the script generates a temporary 4096-bit
self-signed certificate to exercise CLARIN's certificate validation path. Use
SAML_PREFLIGHT_SP_KEY_FILE and SAML_PREFLIGHT_SP_CERT_FILE when you need to
validate the exact certificate that will be submitted to CLARIN.

If the validator container cannot resolve package hosts, set
SAML_PREFLIGHT_DOCKER_DNS to comma- or space-separated DNS servers. If unset,
the script tries DNS_PRIMARY/DNS_SECONDARY and then the rendered compose config.

Pass --generate-only to stop after writing the metadata XML. This is useful
when CI should generate metadata on a deployment host and validate it elsewhere.
EOF
}

die() {
  printf '[saml-preflight] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  local status=$?
  if [[ "${KEEP_WORK_DIR}" != "1" && "${status}" == "0" ]]; then
    if ! rm -rf "${WORK_DIR}"; then
      log "Could not remove work directory: ${WORK_DIR}"
    fi
  else
    log "Keeping work directory: ${WORK_DIR}"
  fi
}
trap cleanup EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

append_docker_dns_server() {
  local dns_server
  dns_server="${1//\"/}"
  dns_server="${dns_server//\'/}"
  dns_server="${dns_server%,}"
  [[ -n "${dns_server}" ]] || return 0
  [[ "${SEEN_DNS_SERVERS}" == *" ${dns_server} "* ]] && return 0

  SEEN_DNS_SERVERS+="${dns_server} "
  DOCKER_DNS_ARGS+=(--dns "${dns_server}")
  return 0
}

collect_compose_dns_servers() {
  local in_dns=0
  local line

  while IFS= read -r line; do
    if [[ "${line}" =~ ^[[:space:]]+dns:[[:space:]]*$ ]]; then
      in_dns=1
      continue
    fi

    if [[ "${in_dns}" == "1" ]]; then
      if [[ "${line}" =~ ^[[:space:]]*-[[:space:]]*([^[:space:]#]+) ]]; then
        append_docker_dns_server "${BASH_REMATCH[1]}"
        continue
      fi

      if [[ "${line}" =~ ^[[:space:]]*[A-Za-z0-9_-]+: ]]; then
        in_dns=0
      fi
    fi
  done < <((cd "${REPO_ROOT}" && docker compose -f "${COMPOSE_FILE_PATH}" config) 2>/dev/null || true)
  return 0
}

build_docker_dns_args() {
  local dns_server
  local configured_dns

  configured_dns="${SAML_PREFLIGHT_DOCKER_DNS:-}"
  configured_dns="${configured_dns//,/ }"
  for dns_server in ${configured_dns}; do
    append_docker_dns_server "${dns_server}"
  done

  if [[ ${#DOCKER_DNS_ARGS[@]} -eq 0 ]]; then
    append_docker_dns_server "${DNS_PRIMARY:-}"
    append_docker_dns_server "${DNS_SECONDARY:-}"
  fi

  if [[ ${#DOCKER_DNS_ARGS[@]} -eq 0 ]]; then
    collect_compose_dns_servers
  fi
  return 0
}

write_metadata_generator() {
  cat > "${WORK_DIR}/generate_saml_metadata.py" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")

import django
from django.conf import settings
from django.test import Client

django.setup()

host = os.environ["SAML_PREFLIGHT_HOST"]
output_path = Path(os.environ["SAML_PREFLIGHT_OUTPUT"])

settings.ALLOWED_HOSTS = list(
    dict.fromkeys([*getattr(settings, "ALLOWED_HOSTS", []), host, "testserver"]),
)

response = Client(HTTP_HOST=host).get("/saml2/metadata/")
if response.status_code != 200:
    sys.stderr.write(response.content.decode("utf-8", "replace"))
    raise SystemExit(f"Metadata endpoint returned HTTP {response.status_code}")

content = response.content
if b"<EntityDescriptor" not in content and b"<md:EntityDescriptor" not in content:
    sys.stderr.write(content[:1000].decode("utf-8", "replace"))
    raise SystemExit("Metadata endpoint did not return a SAML EntityDescriptor")

output_path.write_bytes(content)
print(f"Wrote {len(content)} bytes to {output_path}")
PY
}

generate_dev_certificate() {
  if [[ -n "${SAML_PREFLIGHT_SP_KEY_FILE:-}" && -n "${SAML_PREFLIGHT_SP_CERT_FILE:-}" ]]; then
    cp "${SAML_PREFLIGHT_SP_KEY_FILE}" "${WORK_DIR}/sp-key.pem"
    cp "${SAML_PREFLIGHT_SP_CERT_FILE}" "${WORK_DIR}/sp-cert.pem"
    log "Using SAML_PREFLIGHT_SP_KEY_FILE/SAML_PREFLIGHT_SP_CERT_FILE"
    return
  fi

  if [[ -n "${SAML_SP_KEY_FILE:-}" && -n "${SAML_SP_CERT_FILE:-}" ]]; then
    APP_KEY_FILE="${SAML_SP_KEY_FILE}"
    APP_CERT_FILE="${SAML_SP_CERT_FILE}"
    log "Using SAML_SP_KEY_FILE/SAML_SP_CERT_FILE as container paths"
    return
  fi

  log "Generating temporary 4096-bit SP certificate for local validation"
  if command -v openssl >/dev/null 2>&1; then
    openssl req \
      -x509 \
      -newkey rsa:4096 \
      -sha256 \
      -days 365 \
      -nodes \
      -subj "/CN=${HOST}" \
      -keyout "${WORK_DIR}/sp-key.pem" \
      -out "${WORK_DIR}/sp-cert.pem" >/dev/null 2>&1
    return
  fi

  docker run --rm \
    -v "${WORK_DIR}:/work" \
    -w /work \
    "${TOOL_IMAGE}" \
    bash -lc "set -euo pipefail; export DEBIAN_FRONTEND=noninteractive; apt-get update >/dev/null; apt-get install -y --no-install-recommends openssl >/dev/null; openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes -subj '/CN=${HOST}' -keyout sp-key.pem -out sp-cert.pem >/dev/null 2>&1"
}

generate_metadata() {
  write_metadata_generator

  log "Generating metadata for ${BASE_URL}"
  (
    cd "${REPO_ROOT}"
    docker compose -f "${COMPOSE_FILE_PATH}" run --rm \
      -e "DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS}" \
      -e "SAML_LOGIN_ENABLED=true" \
      -e "SAML_SP_BASE_URL=${BASE_URL}" \
      -e "PUBLIC_BASE_URL=${BASE_URL}" \
      -e "SAML_ENTITY_ID=${BASE_URL}/saml2/metadata/" \
      -e "SAML_ASSERTION_CONSUMER_SERVICE_URL=${BASE_URL}/saml2/acs/" \
      -e "SAML_SINGLE_LOGOUT_SERVICE_URL=${BASE_URL}/saml2/ls/" \
      -e "SAML_REQUEST_INITIATOR_URL=${BASE_URL}/saml2/login/" \
      -e "SAML_DISCOVERY_RESPONSE_URL=${BASE_URL}/saml2/login/" \
      -e "SAML_METADATA_KEY_USAGE=signing" \
      -e "SAML_SP_KEY_FILE=${APP_KEY_FILE}" \
      -e "SAML_SP_CERT_FILE=${APP_CERT_FILE}" \
      -e "SAML_PREFLIGHT_HOST=${HOST}" \
      -e "SAML_PREFLIGHT_OUTPUT=${APP_METADATA_FILE}" \
      "${DJANGO_SERVICE}" \
      python "${APP_GENERATOR}"
  )

  [[ -s "${METADATA_FILE}" ]] || die "Metadata file was not generated"
}

write_validator_runner() {
  cat > "${WORK_DIR}/run_clarin_validators.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

fix_permissions() {
  chown -R "${SAML_PREFLIGHT_HOST_UID:-0}:${SAML_PREFLIGHT_HOST_GID:-0}" /work 2>/dev/null || true
}
trap fix_permissions EXIT

export DEBIAN_FRONTEND=noninteractive
apt-get update >/dev/null
apt-get install -y --no-install-recommends \
  ant \
  ca-certificates \
  default-jdk \
  git \
  libxml2-utils \
  openssl \
  unzip \
  wget >/dev/null

export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(which javac)")")")"

rm -rf /work/spf-sps-metadata /work/qa-tmp
git clone --depth 1 --recurse-submodules \
  https://github.com/clarin-eric/SPF-SPs-metadata.git \
  /work/spf-sps-metadata >/dev/null

cd /work/spf-sps-metadata

echo "== XML schema validation =="
check-saml-metadata/xmlsectool/xmlsectool.sh \
  --validateSchema \
  --schemaDirectory check-saml-metadata/saml-schema \
  --logConfig check-saml-metadata/logger.xml \
  --inFile /work/metadata.xml

echo "== Certificate check =="
CI-assets/check_certificates.sh -f /work/metadata.xml | tee /work/certificate-results.txt

echo "== Schematron QA =="
QA_VALIDATOR_VERSION=1.0.9
SAXON_VERSION=SaxonHE9-9-1-5J
SAXON_URL="https://downloads.sourceforge.net/project/saxon/Saxon-HE/9.9/${SAXON_VERSION}.zip"
SCHEMATRON_VERSION=1.0.1-e16ecc4-CLARIN
INSTALLS_PATH=/work/qa-tmp

mkdir -p "${INSTALLS_PATH}/saxon"
cd "${INSTALLS_PATH}/saxon"
wget -q --no-check-certificate "${SAXON_URL}"
unzip -q -o "${SAXON_VERSION}.zip"
rm "${SAXON_VERSION}.zip"

cd "${INSTALLS_PATH}"
wget -q -O schematron.tar.gz \
  "https://codeload.github.com/clarin-eric/schematron/tar.gz/${SCHEMATRON_VERSION}"
tar xzf schematron.tar.gz "schematron-${SCHEMATRON_VERSION}/trunk/schematron/code/"
mv "schematron-${SCHEMATRON_VERSION}/trunk/schematron/code" schematron
rm -rf "schematron-${SCHEMATRON_VERSION}" schematron.tar.gz

wget -q -O SAML_metadata_QA_validator.tar.gz \
  "https://codeload.github.com/clarin-eric/SAML_metadata_QA_validator/tar.gz/${QA_VALIDATOR_VERSION}"
tar xzf SAML_metadata_QA_validator.tar.gz

cd "${INSTALLS_PATH}/SAML_metadata_QA_validator-${QA_VALIDATOR_VERSION}"
ant -DinputFile="file:/work/metadata.xml" >/work/qa-ant.log

total_errors=0
total_warnings=0
{
  echo "SP entityID | Severity | Requirement | Explanation"
  echo "--- | --- | --- | ---"

  shopt -s nullglob
  for xml in out/*_results.xml; do
    count=$(xmllint --xpath "count(/results/result)" "$xml" 2>/dev/null)
    count="${count%.*}"
    [[ -z "${count}" || "${count}" == "0" ]] && continue

    for i in $(seq 1 "${count}"); do
      sp=$(xmllint --xpath "string(/results/result[$i]/sp)" "$xml" 2>/dev/null)
      requirement=$(xmllint --xpath "string(/results/result[$i]/requirement)" "$xml" 2>/dev/null)
      explanation=$(xmllint --xpath "string(/results/result[$i]/explanation)" "$xml" 2>/dev/null)

      if [[ "${requirement}" == Completely* ]]; then
        severity="error"
        total_errors=$((total_errors + 1))
      else
        severity="warning"
        total_warnings=$((total_warnings + 1))
      fi

      printf '%s | %s | %s | %s\n' "${sp}" "${severity}" "${requirement}" "${explanation}"
    done
  done
  shopt -u nullglob
} | tee /work/qa-results.md

echo "QA errors: ${total_errors}" | tee -a /work/qa-results.md
echo "QA warnings: ${total_warnings}" | tee -a /work/qa-results.md

if (( total_errors > 0 )); then
  exit 20
fi

if [[ "${SAML_PREFLIGHT_FAIL_ON_QA_WARNINGS:-1}" == "1" && "${total_warnings}" -gt 0 ]]; then
  exit 21
fi
SH
  chmod +x "${WORK_DIR}/run_clarin_validators.sh"
}

run_validators() {
  write_validator_runner
  build_docker_dns_args

  if [[ ${#DOCKER_DNS_ARGS[@]} -gt 0 ]]; then
    log "Using validator container DNS servers: ${SEEN_DNS_SERVERS}"
  fi

  log "Running CLARIN validators in disposable ${TOOL_IMAGE} container"
  docker run --rm \
    "${DOCKER_DNS_ARGS[@]}" \
    -e "SAML_PREFLIGHT_FAIL_ON_QA_WARNINGS=${FAIL_ON_QA_WARNINGS}" \
    -e "SAML_PREFLIGHT_HOST_UID=$(id -u)" \
    -e "SAML_PREFLIGHT_HOST_GID=$(id -g)" \
    -v "${WORK_DIR}:/work" \
    -w /work \
    "${TOOL_IMAGE}" \
    bash /work/run_clarin_validators.sh
}

main() {
  local generate_only=0

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  if [[ "${1:-}" == "--generate-only" ]]; then
    generate_only=1
    shift
  fi

  [[ "$#" -eq 0 ]] || die "Unknown arguments. Use --help for usage."

  require_command docker

  rm -rf "${WORK_DIR}"
  mkdir -p "${WORK_DIR}"

  generate_dev_certificate
  generate_metadata

  if [[ "${generate_only}" == "1" ]]; then
    log "Generated metadata only: ${METADATA_FILE}"
    exit 0
  fi

  run_validators

  log "CLARIN preflight passed"
}

main "$@"
