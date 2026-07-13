#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[saml-remote-preflight] %s\n' "$*" >&2
}

die() {
  printf '[saml-remote-preflight] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

[[ "$#" -eq 4 ]] || {
  die "Usage: saml-preflight.sh DEPLOYMENT_DIR BRANCH COMMIT_SHA EXPECTED_USER"
}

deployment_dir=$1
branch=$2
commit=$3
expected_user=$4
worktree_path=
worktree_added=0

cleanup() {
  local status=$?
  if [[ "${worktree_added}" == "1" ]]; then
    git -C "${deployment_dir}" worktree remove --force "${worktree_path}" >/dev/null 2>&1 || true
    git -C "${deployment_dir}" worktree prune >/dev/null 2>&1 || true
  fi
  exit "${status}"
}
trap cleanup EXIT

[[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || die "Commit must be a 40 character lowercase commit SHA"
[[ "${branch}" == "main" ]] || die "SAML production preflight only supports main"
[[ -d "${deployment_dir}/.git" ]] || die "Deployment directory is not a Git checkout: ${deployment_dir}"
[[ "$(id -un)" == "${expected_user}" ]] || die "Preflight must run as ${expected_user}"

require_command flock
require_command git

exec 9>"${deployment_dir}/.deploy.lock"
flock -n 9 || die "Another deployment operation is already in progress"

log "Fetching ${branch} without changing the live checkout"
git -C "${deployment_dir}" fetch --prune --no-tags origin "${branch}"
branch_head="$(git -C "${deployment_dir}" rev-parse "origin/${branch}^{commit}")"
[[ "${branch_head}" == "${commit}" ]] || {
  die "Pipeline commit ${commit} is no longer the head of ${branch}; current head is ${branch_head}"
}
git -C "${deployment_dir}" cat-file -e "${commit}^{commit}" || {
  die "Pipeline commit was not fetched: ${commit}"
}

mkdir -p "${deployment_dir}/.worktrees"
worktree_path="${deployment_dir}/.worktrees/saml-preflight.${BASHPID}"
git -C "${deployment_dir}" worktree add --detach "${worktree_path}" "${commit}" >&2
worktree_added=1

if [[ -d "${deployment_dir}/.envs" ]]; then
  ln -s "${deployment_dir}/.envs" "${worktree_path}/.envs"
fi
if [[ -f "${deployment_dir}/.env" ]]; then
  ln -s "${deployment_dir}/.env" "${worktree_path}/.env"
fi

docker_socket="${DOCKER_SOCKET:-/var/run/docker.sock}"
if [[ -e "${docker_socket}" ]]; then
  export DOCKER_GID
  DOCKER_GID="$(stat -c '%g' "${docker_socket}")"
fi

export COMPOSE_PROJECT_NAME="${DEPLOY_COMPOSE_PROJECT_NAME:-$(basename "${deployment_dir}")}"
export SAML_PREFLIGHT_COMPOSE_FILE=docker-compose.production.yml
export SAML_PREFLIGHT_DJANGO_SETTINGS=config.settings.production
export SAML_PREFLIGHT_SP_KEY_FILE=/etc/shibboleth/prod-sp-key.pem
export SAML_PREFLIGHT_SP_CERT_FILE=/etc/shibboleth/prod-sp-cert.pem
export SAML_PREFLIGHT_BASE_URL=https://lac.uni-koeln.de
export SAML_PREFLIGHT_KEEP_WORK_DIR=1
export SAML_PREFLIGHT_WORK_DIR="${worktree_path}/.tmp/saml-preflight"

generator="${SAML_PREFLIGHT_GENERATOR:-./scripts/validate_saml_metadata.sh}"
log "Generating metadata from isolated commit ${commit}"
(
  cd "${worktree_path}"
  "${generator}" --generate-only
) >&2

metadata_file="${SAML_PREFLIGHT_WORK_DIR}/metadata.xml"
[[ -s "${metadata_file}" ]] || die "Metadata file was not generated"
cat "${metadata_file}"
