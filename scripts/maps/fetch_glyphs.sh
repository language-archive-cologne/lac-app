#!/usr/bin/env bash
# Download pre-built Noto Sans PBF glyph ranges from protomaps/basemaps-assets
# (MIT licensed). Output: ./build/maps/glyphs/<fontstack>/<range>.pbf
# The style JSON only references "Noto Sans Regular", so that's all we fetch.
set -euo pipefail

OUT_DIR="${OUT_DIR:-$(pwd)/build/maps/glyphs}"
STACK="${STACK:-Noto Sans Regular}"
REF="${REF:-main}"

mkdir -p "${OUT_DIR}"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

echo "→ Downloading protomaps/basemaps-assets@${REF}…"
TAR="${WORK_DIR}/basemaps-assets.tar.gz"
curl --retry 3 -fSL -o "${TAR}" \
  "https://github.com/protomaps/basemaps-assets/archive/refs/heads/${REF}.tar.gz"

echo "→ Extracting ${STACK}…"
mkdir -p "${OUT_DIR}/${STACK}"
tar -xzf "${TAR}" -C "${WORK_DIR}" \
  --strip-components=2 \
  "basemaps-assets-${REF}/fonts/${STACK}/"
mv "${WORK_DIR}/${STACK}"/*.pbf "${OUT_DIR}/${STACK}/"

count=$(find "${OUT_DIR}/${STACK}" -name "*.pbf" | wc -l)
echo "✓ ${STACK}: ${count} PBFs in ${OUT_DIR}/${STACK}/"
