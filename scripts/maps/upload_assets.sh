#!/usr/bin/env bash
# Upload ./build/maps/ to the lacos-maps bucket.
# Target bucket layout:
#   /ne.pmtiles
#   /glyphs/<fontstack>/<range>.pbf
set -euo pipefail

BUCKET="${BUCKET:-lacos-maps}"
ENDPOINT="${S3_ENDPOINT:-http://localhost:9100}"
ACCESS_KEY="${S3_ACCESS_KEY:-minioadmin}"
SECRET_KEY="${S3_SECRET_KEY:-minioadmin}"
ALIAS="${MC_ALIAS:-lac}"
BUILD_DIR="${BUILD_DIR:-$(pwd)/build/maps}"

if [[ ! -f "${BUILD_DIR}/ne.pmtiles" ]]; then
  echo "✗ Missing ${BUILD_DIR}/ne.pmtiles — run build_pmtiles.sh first." >&2
  exit 1
fi
if [[ ! -d "${BUILD_DIR}/glyphs" ]]; then
  echo "✗ Missing ${BUILD_DIR}/glyphs/ — run build_glyphs.sh first." >&2
  exit 1
fi

MC="docker run --rm -i --network=host \
  -v ${BUILD_DIR}:/artifacts:ro \
  -e MC_HOST_${ALIAS}=${ENDPOINT//:\/\//:\/\/${ACCESS_KEY}:${SECRET_KEY}@} \
  minio/mc:latest"

echo "→ Uploading ne.pmtiles…"
${MC} cp --attr "Cache-Control=public,max-age=604800,immutable" \
  /artifacts/ne.pmtiles "${ALIAS}/${BUCKET}/ne.pmtiles"

echo "→ Uploading glyph PBFs…"
${MC} mirror --overwrite --attr "Cache-Control=public,max-age=2592000,immutable" \
  /artifacts/glyphs/ "${ALIAS}/${BUCKET}/glyphs/"

echo "✓ Uploaded to ${ENDPOINT}/${BUCKET}/"
${MC} ls "${ALIAS}/${BUCKET}/"
