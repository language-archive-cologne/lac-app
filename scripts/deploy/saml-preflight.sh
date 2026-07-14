#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly PRODUCTION_ENV_FILENAMES=(.django .postgres .storage)

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

validate_private_path() {
  local description=$1
  local path=$2
  local mode
  local owner_uid

  owner_uid="$(stat -c '%u' -- "${path}")"
  [[ "${owner_uid}" == "$(id -u)" ]] || {
    die "${description} must be owned by the deployment user: ${path}"
  }

  mode="$(stat -c '%a' -- "${path}")"
  [[ "${mode: -2}" == "00" ]] || {
    die "${description} must not grant group or other permissions: ${path} (mode ${mode})"
  }
}

validate_production_environment() {
  local env_file
  local production_env_dir=$1

  [[ -d "${production_env_dir}" ]] || {
    die "Production environment directory is missing: ${production_env_dir}"
  }
  [[ ! -L "${production_env_dir}" ]] || {
    die "Production environment directory must not be a symlink: ${production_env_dir}"
  }
  validate_private_path "Production environment directory" "${production_env_dir}"

  for env_file in "${PRODUCTION_ENV_FILENAMES[@]}"; do
    env_file="${production_env_dir}/${env_file}"
    [[ -f "${env_file}" ]] || {
      die "Production environment file is missing: ${env_file}"
    }
    [[ ! -L "${env_file}" ]] || {
      die "Production environment file must not be a symlink: ${env_file}"
    }
    validate_private_path "Production environment file" "${env_file}"
  done
}

prepare_worktree_environment() {
  local env_filename
  local production_env_dir=$1
  local worktree_path=$2
  local deployment_dir=$3
  local worktree_production_env_dir="${worktree_path}/.envs/.production"

  [[ -d "${worktree_path}/.envs" ]] || {
    die "Commit does not contain the expected .envs directory"
  }
  [[ ! -L "${worktree_path}/.envs" ]] || {
    die "Commit contains an unsafe .envs symlink"
  }
  [[ ! -e "${worktree_production_env_dir}" && ! -L "${worktree_production_env_dir}" ]] || {
    die "Commit contains an unexpected .envs/.production path"
  }

  install -d -m 0700 "${worktree_production_env_dir}"
  for env_filename in "${PRODUCTION_ENV_FILENAMES[@]}"; do
    ln -s -- \
      "${production_env_dir}/${env_filename}" \
      "${worktree_production_env_dir}/${env_filename}"
  done

  if [[ -L "${deployment_dir}/.env" ]]; then
    die "Deployment .env must not be a symlink: ${deployment_dir}/.env"
  fi
  if [[ -f "${deployment_dir}/.env" ]]; then
    ln -s -- "${deployment_dir}/.env" "${worktree_path}/.env"
  fi
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
require_command install
require_command stat

production_env_dir="${deployment_dir}/.envs/.production"

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
validate_production_environment "${production_env_dir}"

install -d -m 0700 "${deployment_dir}/.worktrees"
worktree_path="${deployment_dir}/.worktrees/saml-preflight.${BASHPID}"
git -C "${deployment_dir}" worktree add --detach "${worktree_path}" "${commit}" >&2
worktree_added=1

prepare_worktree_environment \
  "${production_env_dir}" \
  "${worktree_path}" \
  "${deployment_dir}"

docker_socket="${DOCKER_SOCKET:-/var/run/docker.sock}"
if [[ -e "${docker_socket}" ]]; then
  export DOCKER_GID
  DOCKER_GID="$(stat -c '%g' "${docker_socket}")"
fi

export COMPOSE_PROJECT_NAME="${DEPLOY_COMPOSE_PROJECT_NAME:-$(basename "${deployment_dir}")}"
export SAML_PREFLIGHT_COMPOSE_FILE=docker-compose.production.yml
export SAML_PREFLIGHT_DJANGO_SETTINGS=config.settings.production
export SAML_SP_KEY_FILE=/etc/shibboleth/prod-sp-key.pem
export SAML_SP_CERT_FILE=/etc/shibboleth/prod-sp-cert.pem
export SAML_PREFLIGHT_BASE_URL=https://lac.uni-koeln.de
export SAML_PREFLIGHT_ROOT_GENERATOR=1
export SAML_PREFLIGHT_KEEP_WORK_DIR=1
export SAML_PREFLIGHT_REPO_ROOT="${worktree_path}"
export SAML_PREFLIGHT_WORK_DIR="${worktree_path}/.tmp/saml-preflight"

generator="${SAML_PREFLIGHT_GENERATOR:-./scripts/validate_saml_metadata.sh}"
log "Generating metadata from isolated commit ${commit}"
(
  cd "${worktree_path}"
  "${generator}" --generate-only
) >&2

metadata_file="${SAML_PREFLIGHT_WORK_DIR}/metadata.xml"
[[ -s "${metadata_file}" ]] || die "Metadata file was not generated"
log "Streaming generated metadata ($(stat -c '%s' -- "${metadata_file}") bytes)"
cat "${metadata_file}"
