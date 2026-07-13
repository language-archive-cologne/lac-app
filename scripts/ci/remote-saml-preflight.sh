#!/usr/bin/env bash
set -euo pipefail

die() {
  printf '[remote-saml-preflight] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$#" -eq 1 ]] || die "Usage: remote-saml-preflight.sh COMMIT_SHA"

commit=$1
expected_user=lacos-prod-deploy
[[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || die "Commit must be a 40 character lowercase commit SHA"
[[ "${DEPLOY_USER:-}" == "${expected_user}" ]] || {
  die "Production preflight must use the dedicated ${expected_user} account"
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ssh_config="${SSH_CONFIG_FILE:-${HOME}/.ssh/config}"

ssh -F "${ssh_config}" lac-deployment \
  bash -s -- \
  /opt/lacos/lac-app-production \
  main \
  "${commit}" \
  "${expected_user}" \
  < "${repo_root}/scripts/deploy/saml-preflight.sh"
