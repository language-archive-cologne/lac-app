#!/usr/bin/env bash
# Provision the lacos-maps bucket with public-read + permissive CORS.
# Defaults target local MinIO; override MC_HOST / S3_ENDPOINT for prod.
set -euo pipefail

BUCKET="${BUCKET:-lacos-maps}"
ENDPOINT="${S3_ENDPOINT:-http://localhost:9100}"
ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
SECRET_KEY="${S3_SECRET_KEY:-minioadmin}"
ALIAS="${MC_ALIAS:-lac}"

# mc = MinIO client (works against any S3-compatible API, including AWS).
MC="docker run --rm -i --network=host \
  -e MC_HOST_${ALIAS}=${ENDPOINT//:\/\//:\/\/${ACCESS_KEY}:${SECRET_KEY}@} \
  minio/mc:latest"

echo "→ Creating bucket: ${BUCKET}"
${MC} mb --ignore-existing "${ALIAS}/${BUCKET}"

echo "→ Setting public-read anonymous policy (GET + HEAD only)…"
${MC} anonymous set download "${ALIAS}/${BUCKET}"

echo "→ Installing CORS rule (GET + HEAD + Range, any origin)…"
# CORS JSON; MinIO accepts the same schema as AWS S3.
TMP_CORS="$(mktemp)"
trap 'rm -f "${TMP_CORS}"' EXIT
cat > "${TMP_CORS}" <<'JSON'
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag", "Content-Length", "Content-Range", "Accept-Ranges"],
      "MaxAgeSeconds": 3600
    }
  ]
}
JSON
${MC} cors set "${ALIAS}/${BUCKET}" "${TMP_CORS}" || \
  echo "⚠ cors set unsupported on this mc version — MinIO's env-level CORS (MINIO_API_ALLOW_CORS_ORIGIN) stays in effect."

echo "✓ Bucket ${BUCKET} ready at ${ENDPOINT}"
