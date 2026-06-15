#!/usr/bin/env bash
# Validate an existing SAML metadata XML file with CLARIN's automated checks.
#
# This script expects Java, Ant, git, xmllint, openssl, unzip, and wget to
# already be installed in the current environment.
set -euo pipefail

FAIL_ON_QA_WARNINGS="${SAML_PREFLIGHT_FAIL_ON_QA_WARNINGS:-1}"
QA_VALIDATOR_VERSION="${SAML_PREFLIGHT_QA_VALIDATOR_VERSION:-1.0.9}"
SAXON_VERSION="${SAML_PREFLIGHT_SAXON_VERSION:-SaxonHE9-9-1-5J}"
SCHEMATRON_VERSION="${SAML_PREFLIGHT_SCHEMATRON_VERSION:-1.0.1-e16ecc4-CLARIN}"
WORK_DIR="${SAML_PREFLIGHT_VALIDATOR_WORK_DIR:-}"
KEEP_WORK_DIR="${SAML_PREFLIGHT_KEEP_WORK_DIR:-0}"
CREATED_WORK_DIR=0

log() {
  printf '[saml-validator] %s\n' "$*"
}

die() {
  printf '[saml-validator] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: scripts/validate_saml_metadata_file.sh path/to/metadata.xml

Validates one generated SAML metadata XML file with CLARIN's automated checks:
  - xmlsectool SAML schema validation
  - CLARIN certificate key-size and expiry check
  - CLARIN Schematron metadata QA

Required commands: bash, git, java, ant, xmllint, openssl, unzip, wget.
Useful environment variables:
  SAML_PREFLIGHT_FAIL_ON_QA_WARNINGS=0
  SAML_PREFLIGHT_KEEP_WORK_DIR=1
  SAML_PREFLIGHT_VALIDATOR_WORK_DIR=/tmp/saml-validator
EOF
}

cleanup() {
  local status=$?
  if [[ "${CREATED_WORK_DIR}" == "1" && "${KEEP_WORK_DIR}" != "1" && "${status}" == "0" ]]; then
    rm -rf "${WORK_DIR}" || true
  elif [[ "${KEEP_WORK_DIR}" == "1" ]]; then
    log "Keeping work directory: ${WORK_DIR}"
  fi
}
trap cleanup EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

absolute_path() {
  local path=$1
  local dir
  local base

  dir="$(cd "$(dirname "${path}")" && pwd)"
  base="$(basename "${path}")"
  printf '%s/%s\n' "${dir}" "${base}"
}

validate_metadata_file() {
  local metadata_file=$1
  local installs_path
  local saxon_url
  local total_errors=0
  local total_warnings=0
  local count
  local sp
  local requirement
  local explanation
  local severity

  installs_path="${WORK_DIR}/qa-tmp"
  saxon_url="https://downloads.sourceforge.net/project/saxon/Saxon-HE/9.9/${SAXON_VERSION}.zip"

  rm -rf "${WORK_DIR}/spf-sps-metadata" "${installs_path}"
  git clone --depth 1 --recurse-submodules \
    https://github.com/clarin-eric/SPF-SPs-metadata.git \
    "${WORK_DIR}/spf-sps-metadata" >/dev/null

  cd "${WORK_DIR}/spf-sps-metadata"

  echo "== XML schema validation =="
  check-saml-metadata/xmlsectool/xmlsectool.sh \
    --validateSchema \
    --schemaDirectory check-saml-metadata/saml-schema \
    --logConfig check-saml-metadata/logger.xml \
    --inFile "${metadata_file}"

  echo "== Certificate check =="
  CI-assets/check_certificates.sh -f "${metadata_file}" | tee "${WORK_DIR}/certificate-results.txt"

  echo "== Schematron QA =="
  mkdir -p "${installs_path}/saxon"
  cd "${installs_path}/saxon"
  wget -q --no-check-certificate "${saxon_url}"
  unzip -q -o "${SAXON_VERSION}.zip"
  rm "${SAXON_VERSION}.zip"

  cd "${installs_path}"
  wget -q -O schematron.tar.gz \
    "https://codeload.github.com/clarin-eric/schematron/tar.gz/${SCHEMATRON_VERSION}"
  tar xzf schematron.tar.gz "schematron-${SCHEMATRON_VERSION}/trunk/schematron/code/"
  mv "schematron-${SCHEMATRON_VERSION}/trunk/schematron/code" schematron
  rm -rf "schematron-${SCHEMATRON_VERSION}" schematron.tar.gz

  wget -q -O SAML_metadata_QA_validator.tar.gz \
    "https://codeload.github.com/clarin-eric/SAML_metadata_QA_validator/tar.gz/${QA_VALIDATOR_VERSION}"
  tar xzf SAML_metadata_QA_validator.tar.gz

  cd "${installs_path}/SAML_metadata_QA_validator-${QA_VALIDATOR_VERSION}"
  ant -DinputFile="file:${metadata_file}" >"${WORK_DIR}/qa-ant.log"

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
  } | tee "${WORK_DIR}/qa-results.md"

  echo "QA errors: ${total_errors}" | tee -a "${WORK_DIR}/qa-results.md"
  echo "QA warnings: ${total_warnings}" | tee -a "${WORK_DIR}/qa-results.md"

  if (( total_errors > 0 )); then
    exit 20
  fi

  if [[ "${FAIL_ON_QA_WARNINGS}" == "1" && "${total_warnings}" -gt 0 ]]; then
    exit 21
  fi
}

main() {
  local metadata_file

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi
  [[ "$#" -eq 1 ]] || die "Expected exactly one metadata XML file. Use --help for usage."

  metadata_file="$(absolute_path "$1")"
  [[ -s "${metadata_file}" ]] || die "Metadata file does not exist or is empty: ${metadata_file}"

  require_command bash
  require_command git
  require_command java
  require_command ant
  require_command xmllint
  require_command openssl
  require_command unzip
  require_command wget

  export JAVA_HOME="${JAVA_HOME:-$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")}"

  if [[ -z "${WORK_DIR}" ]]; then
    WORK_DIR="$(mktemp -d)"
    CREATED_WORK_DIR=1
  fi
  mkdir -p "${WORK_DIR}"

  validate_metadata_file "${metadata_file}"
  log "CLARIN metadata file validation passed"
}

main "$@"
