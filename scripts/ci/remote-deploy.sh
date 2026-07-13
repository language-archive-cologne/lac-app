#!/usr/bin/env bash
set -euo pipefail

die() {
  printf '[remote-deploy] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$#" -eq 3 ]] || die "Usage: remote-deploy.sh ENVIRONMENT MODE COMMIT_SHA"

environment=$1
mode=$2
commit=$3

case "${environment}" in
  development)
    deployment_dir=/opt/lacos/lac-app
    compose_file=docker-compose.dev.yml
    branch=dev
    expected_user=lacos-dev-deploy
    ;;
  production)
    deployment_dir=/opt/lacos/lac-app-production
    compose_file=docker-compose.production.yml
    branch=main
    expected_user=lacos-prod-deploy
    ;;
  *)
    die "Unsupported environment: ${environment}"
    ;;
esac

[[ "${mode}" == "full" || "${mode}" == "fast" ]] || die "Unsupported deployment mode: ${mode}"
[[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || die "Commit must be a 40 character lowercase commit SHA"
[[ "${DEPLOY_USER:-}" == "${expected_user}" ]] || {
  die "${environment} must use the dedicated ${expected_user} account"
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ssh_config="${SSH_CONFIG_FILE:-${HOME}/.ssh/config}"
theme_artifact="${THEME_ARTIFACT_FILE:-${repo_root}/theme/static/css/output.css}"
remote_theme_artifact="${deployment_dir}/.theme-output.${commit}.css"

[[ -s "${theme_artifact}" ]] || die "Validated theme artifact is missing or empty: ${theme_artifact}"

cleanup_upload() {
  ssh -F "${ssh_config}" lac-deployment \
    rm -f -- "${remote_theme_artifact}" >/dev/null 2>&1 || true
}
trap cleanup_upload EXIT

scp -F "${ssh_config}" \
  "${theme_artifact}" \
  "lac-deployment:${remote_theme_artifact}"

ssh -F "${ssh_config}" lac-deployment \
  bash -s -- \
  "${deployment_dir}" \
  "${compose_file}" \
  "${branch}" \
  "${commit}" \
  "${mode}" \
  "${expected_user}" \
  "${remote_theme_artifact}" \
  < "${repo_root}/scripts/deploy/deploy.sh"

trap - EXIT
