#!/usr/bin/env bash
set -euo pipefail

die() {
  printf '[configure-ssh] ERROR: %s\n' "$*" >&2
  exit 1
}

require_file_variable() {
  local name=$1
  local value=${!name:-}

  [[ -n "${value}" ]] || die "${name} must be configured as a GitLab file variable"
  [[ -s "${value}" ]] || die "${name} does not point to a readable nonempty file"
}

[[ -n "${DEPLOY_HOST:-}" ]] || die "DEPLOY_HOST is required"
[[ -n "${DEPLOY_USER:-}" ]] || die "DEPLOY_USER is required"
[[ "${DEPLOY_HOST}" =~ ^[A-Za-z0-9._:-]+$ ]] || die "DEPLOY_HOST contains unsafe characters"
[[ "${DEPLOY_USER}" =~ ^[a-z_][a-z0-9_-]*$ ]] || die "DEPLOY_USER contains unsafe characters"
require_file_variable SSH_PRIVATE_KEY
require_file_variable SSH_KNOWN_HOSTS

ssh_dir="${HOME}/.ssh"
mkdir -p "${ssh_dir}"
chmod 700 "${ssh_dir}"
cp "${SSH_PRIVATE_KEY}" "${ssh_dir}/deploy_key"
cp "${SSH_KNOWN_HOSTS}" "${ssh_dir}/known_hosts"
chmod 600 "${ssh_dir}/deploy_key" "${ssh_dir}/known_hosts"

cat > "${ssh_dir}/config" <<EOF
Host lac-deployment
  HostName ${DEPLOY_HOST}
  User ${DEPLOY_USER}
  IdentityFile ${ssh_dir}/deploy_key
  BatchMode yes
  IdentitiesOnly yes
  IdentityAgent none
  StrictHostKeyChecking yes
  UserKnownHostsFile ${ssh_dir}/known_hosts
EOF
chmod 600 "${ssh_dir}/config"
