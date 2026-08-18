#!/usr/bin/env bash
set -euo pipefail

die() {
  printf '[verify-nginx-config] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$#" -ge 2 && "$#" -le 3 ]] || {
  die "Usage: verify-nginx-config.sh EXPECTED INSTALLED [PRIVATE_CONFIG_DIR]"
}

expected=$1
installed=$2
private_config_dir=${3:-/etc/nginx/lacos-private}

require_directive() {
  local config_file=$1
  local pattern=$2
  local description=$3
  grep -Eq -- "${pattern}" "${config_file}" || {
    die "Private Nginx config is missing ${description}: ${config_file}"
  }
}

require_connection_ceiling() {
  local config_file=$1
  local zone=$2
  local maximum=$3
  local description=$4
  local directive
  local value

  directive="$(
    grep -Em1 -- \
      "^[[:space:]]*limit_conn[[:space:]]+${zone}[[:space:]]+[0-9]+;" \
      "${config_file}"
  )" || die "Private Nginx config has no numeric ${description}: ${config_file}"
  value="$(awk '{gsub(/;/, "", $3); print $3}' <<<"${directive}")"
  (( value > 0 )) || die "Private Nginx ${description} must be positive"
  (( value <= maximum )) || {
    die "Private Nginx ${description} exceeds safe maximum ${maximum}"
  }
}

[[ -f "${expected}" ]] || die "Expected config does not exist: ${expected}"
[[ -f "${installed}" ]] || die "Installed config does not exist: ${installed}"

cmp -s -- "${expected}" "${installed}" || {
  die "Installed Nginx config differs from reviewed config: ${installed}"
}

while IFS= read -r included_file; do
  private_file="${private_config_dir}/$(basename "${included_file}")"
  [[ -e "${private_file}" ]] || {
    die "Private Nginx config does not exist: ${private_file}"
  }
  [[ -s "${private_file}" ]] || {
    die "Private Nginx config is empty: ${private_file}"
  }
  case "$(basename "${included_file}")" in
    search-zones.conf)
      require_directive "${private_file}" 'limit_req_zone .*zone=lacos_search_per_ip:' 'the per-client request zone'
      require_directive "${private_file}" 'limit_req_zone .*zone=lacos_search_emergency_requests:' 'the search emergency request zone'
      require_directive "${private_file}" 'limit_conn_zone .*zone=lacos_search_emergency_connections:' 'the search emergency connection zone'
      require_directive "${private_file}" 'limit_req_zone .*zone=lacos_application_emergency_requests:' 'the application emergency request zone'
      require_directive "${private_file}" 'limit_conn_zone .*zone=lacos_application_emergency_connections:' 'the application emergency connection zone'
      require_directive "${private_file}" 'map .*\$lacos_search_too_many_keywords' 'the excessive-query map'
      require_directive "${private_file}" 'map .*\$lacos_search_retry_after' 'the search retry value'
      require_directive "${private_file}" 'map .*\$lacos_capacity_retry_after' 'the capacity retry value'
      ;;
    search-location-limits.conf)
      require_directive "${private_file}" 'limit_req zone=lacos_search_per_ip ' 'the per-client search boundary'
      require_directive "${private_file}" 'limit_req zone=lacos_search_emergency_requests ' 'the search emergency request boundary'
      require_directive "${private_file}" 'limit_conn lacos_search_emergency_connections ' 'the search emergency connection boundary'
      require_connection_ceiling \
        "${private_file}" \
        lacos_search_emergency_connections \
        12 \
        'search connection ceiling'
      ;;
    application-location-limits.conf)
      require_directive "${private_file}" 'limit_req zone=lacos_application_emergency_requests ' 'the application emergency request boundary'
      require_directive "${private_file}" 'limit_conn lacos_application_emergency_connections ' 'the application emergency connection boundary'
      require_connection_ceiling \
        "${private_file}" \
        lacos_application_emergency_connections \
        20 \
        'application connection ceiling'
      ;;
  esac
done < <(
  awk '$1 == "include" && $2 ~ /^\/etc\/nginx\/lacos-private\// {
    gsub(/;$/, "", $2)
    print $2
  }' "${expected}"
)
