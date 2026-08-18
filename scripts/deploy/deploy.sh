#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[deploy] %s\n' "$*"
}

die() {
  printf '[deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

[[ "$#" -eq 7 ]] || {
  die "Usage: deploy.sh DEPLOYMENT_DIR COMPOSE_FILE BRANCH COMMIT_SHA MODE EXPECTED_USER THEME_ARTIFACT"
}

deployment_dir=$1
compose_file=$2
branch=$3
commit=$4
mode=$5
expected_user=$6
theme_artifact=$7

[[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || die "Commit must be a 40 character lowercase commit SHA"
[[ "${branch}" == "dev" || "${branch}" == "main" ]] || die "Unsupported branch: ${branch}"
[[ "${mode}" == "full" || "${mode}" == "fast" ]] || die "Unsupported deployment mode: ${mode}"
[[ "${compose_file}" != */* ]] || die "Compose file must be located at the repository root"
[[ -d "${deployment_dir}/.git" ]] || die "Deployment directory is not a Git checkout: ${deployment_dir}"
[[ "$(id -un)" == "${expected_user}" ]] || die "Deployment must run as ${expected_user}"
expected_theme_artifact="${deployment_dir}/.theme-output.${commit}.css"
[[ "${theme_artifact}" == "${expected_theme_artifact}" ]] || die "Unexpected theme artifact path"
[[ -s "${theme_artifact}" ]] || die "Theme artifact is missing or empty"

theme_destination="${deployment_dir}/theme/static/css/output.css"
theme_temporary=

cleanup() {
  local status=$?
  rm -f -- "${theme_artifact}"
  if [[ -n "${theme_temporary}" ]]; then
    rm -f -- "${theme_temporary}"
  fi
  exit "${status}"
}
trap cleanup EXIT

require_command docker
require_command flock
require_command git
require_command install
require_command stat

exec 9>"${deployment_dir}/.deploy.lock"
flock -n 9 || die "Another deployment is already in progress"

cd "${deployment_dir}"
log "Fetching ${branch} and validating pipeline commit ${commit}"
git fetch --prune --no-tags origin "${branch}"
branch_head="$(git rev-parse "origin/${branch}^{commit}")"
[[ "${branch_head}" == "${commit}" ]] || {
  die "Pipeline commit ${commit} is no longer the head of ${branch}; current head is ${branch_head}"
}
git cat-file -e "${commit}^{commit}" || die "Pipeline commit was not fetched: ${commit}"
git reset --hard "${commit}"
deployed_head="$(git rev-parse HEAD)"
[[ "${deployed_head}" == "${commit}" ]] || die "Checkout did not reset to ${commit}"

[[ -f "${compose_file}" ]] || die "Compose file does not exist: ${compose_file}"
docker_socket="${DOCKER_SOCKET:-/var/run/docker.sock}"
[[ -e "${docker_socket}" ]] || die "Docker socket does not exist: ${docker_socket}"
export DOCKER_GID
DOCKER_GID="$(stat -c '%g' "${docker_socket}")"

if [[ "${branch}" == "main" ]]; then
  log "Verifying reviewed production Nginx configuration"
  bash scripts/deploy/verify-nginx-config.sh \
    config/nginx/lacos.uni-koeln.de \
    /etc/nginx/sites-enabled/lacos.uni-koeln.de
fi

log "Installing validated theme artifact"
mkdir -p "$(dirname "${theme_destination}")"
theme_temporary="${theme_destination}.${BASHPID}"
install -m 0644 "${theme_artifact}" "${theme_temporary}"
mv -f "${theme_temporary}" "${theme_destination}"
theme_temporary=
[[ -s "${theme_destination}" ]] || die "Theme artifact installation failed"

log "Ensuring the bounded Django cache is available"
docker compose -f "${compose_file}" up \
  -d \
  --no-build \
  --wait \
  --wait-timeout 120 \
  cache </dev/null

if [[ "${mode}" == "full" ]]; then
  log "Rebuilding Django and Huey"
  docker compose -f "${compose_file}" build django huey </dev/null
  docker compose -f "${compose_file}" stop -t 30 huey </dev/null
  docker compose -f "${compose_file}" up \
    -d \
    --no-deps \
    --force-recreate \
    --wait \
    --wait-timeout 120 \
    django </dev/null
  docker compose -f "${compose_file}" up \
    -d \
    --no-deps \
    --force-recreate \
    --wait \
    --wait-timeout 120 \
    huey </dev/null
else
  log "Restarting Django and Huey without rebuilding images"
  docker compose -f "${compose_file}" stop -t 30 huey </dev/null
  docker compose -f "${compose_file}" up \
    -d \
    --no-build \
    --no-deps \
    --force-recreate \
    --wait \
    --wait-timeout 120 \
    django </dev/null
  docker compose -f "${compose_file}" up \
    -d \
    --no-build \
    --no-deps \
    --wait \
    --wait-timeout 120 \
    huey </dev/null
fi

log "Refreshing Explorer facet caches"
docker compose -f "${compose_file}" exec -T django \
  python manage.py warm_explorer_facets --refresh </dev/null

log "Deployed ${commit}"
