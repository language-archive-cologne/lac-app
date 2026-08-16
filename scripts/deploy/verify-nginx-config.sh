#!/usr/bin/env bash
set -euo pipefail

die() {
  printf '[verify-nginx-config] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$#" -eq 2 ]] || die "Usage: verify-nginx-config.sh EXPECTED INSTALLED"

expected=$1
installed=$2

[[ -f "${expected}" ]] || die "Expected config does not exist: ${expected}"
[[ -f "${installed}" ]] || die "Installed config does not exist: ${installed}"

cmp -s -- "${expected}" "${installed}" || {
  die "Installed Nginx config differs from reviewed config: ${installed}"
}
