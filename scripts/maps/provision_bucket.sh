#!/usr/bin/env bash
# Provision the lacos-maps bucket with public-read + permissive CORS.
# Defaults target local MinIO; override MC_HOST / S3_ENDPOINT for prod.
set -euo pipefail

BUCKET="${BUCKET:-lacos-maps}"
ENDPOINT="${S3_ENDPOINT:-http://localhost:9100}"
ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
SECRET_KEY="${S3_SECRET_KEY:-minioadmin}"
ALIAS="${MC_ALIAS:-lac}"

# Host-side temp dir for passing the CORS JSON into the mc container.
# Created up front so both the setup and the `mc cors set` call can see it.
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

# `mc cors set` expects AWS-S3 CORS XML, not JSON.
cat > "${TMP_DIR}/cors.xml" <<'XML'
<?xml version="1.0" encoding="UTF-8"?>
<CORSConfiguration>
  <CORSRule>
    <AllowedOrigin>*</AllowedOrigin>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedMethod>HEAD</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
    <ExposeHeader>ETag</ExposeHeader>
    <ExposeHeader>Content-Length</ExposeHeader>
    <ExposeHeader>Content-Range</ExposeHeader>
    <ExposeHeader>Accept-Ranges</ExposeHeader>
    <MaxAgeSeconds>3600</MaxAgeSeconds>
  </CORSRule>
</CORSConfiguration>
XML

# mc = MinIO client (works against any S3-compatible API, including AWS).
# Mount TMP_DIR so `mc cors set` can read the XML from inside the container.
MC="docker run --rm -i --network=host \
  -v ${TMP_DIR}:/cors:ro \
  -e MC_HOST_${ALIAS}=${ENDPOINT//:\/\//:\/\/${ACCESS_KEY}:${SECRET_KEY}@} \
  minio/mc:latest"

echo "→ Creating bucket: ${BUCKET}"
${MC} mb --ignore-existing "${ALIAS}/${BUCKET}"

echo "→ Setting public-read anonymous policy (GET + HEAD only)…"
${MC} anonymous set download "${ALIAS}/${BUCKET}"

echo "→ Installing CORS rule (GET + HEAD + Range, any origin)…"
# MinIO does not implement `cors set` (error: "functionality not implemented");
# it enforces CORS via the MINIO_API_ALLOW_CORS_ORIGIN env var instead — set
# in docker-compose.local.yml for dev. For real S3 (AWS or an S3-compatible
# backend that supports the bucket CORS API) this call succeeds.
if ! ${MC} cors set "${ALIAS}/${BUCKET}" /cors/cors.xml; then
  echo "⚠ 'cors set' not supported by this backend."
  echo "  MinIO: relies on MINIO_API_ALLOW_CORS_ORIGIN (see docker-compose.local.yml)."
  echo "  Other S3 backends: configure CORS at the bucket/gateway level out-of-band."
fi

echo "✓ Bucket ${BUCKET} ready at ${ENDPOINT}"
