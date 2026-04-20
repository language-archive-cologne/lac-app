#!/usr/bin/env bash
# Build Natural Earth → ne.pmtiles using tippecanoe.
# Run this offline (e.g. on your laptop). Outputs to ./build/maps/ne.pmtiles.
# Requires: docker.
set -euo pipefail

OUT_DIR="${OUT_DIR:-$(pwd)/build/maps}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

mkdir -p "${OUT_DIR}"
cd "${WORK_DIR}"

# Natural Earth downloads (public domain).
NE_BASE="https://naciscdn.org/naturalearth"

declare -a LAYERS=(
  "110m/cultural/ne_110m_admin_0_countries.zip"
  "110m/cultural/ne_110m_admin_0_boundary_lines_land.zip"
  "110m/physical/ne_110m_ocean.zip"
  "110m/physical/ne_110m_graticules_10.zip"
  "50m/cultural/ne_50m_admin_0_countries.zip"
  "50m/cultural/ne_50m_admin_0_boundary_lines_land.zip"
  "50m/cultural/ne_50m_admin_1_states_provinces_lines.zip"
  "50m/physical/ne_50m_ocean.zip"
  "50m/physical/ne_50m_lakes.zip"
  "50m/physical/ne_50m_rivers_lake_centerlines.zip"
  "50m/physical/ne_50m_coastline.zip"
)

echo "→ Downloading Natural Earth shapefiles…"
for path in "${LAYERS[@]}"; do
  url="${NE_BASE}/${path}"
  zip="$(basename "${path}")"
  curl --retry 3 -fSL -o "${zip}" "${url}"
  unzip -q -o "${zip}"
done

echo "→ Converting shapefiles → NDJSON (via ogr2ogr)…"
shopt -s nullglob
for shp in ne_*.shp; do
  layer="${shp%.shp}"
  docker run --rm -v "$(pwd):/work" -w /work \
    ghcr.io/osgeo/gdal:alpine-small-latest \
    ogr2ogr -f GeoJSONSeq "/work/${layer}.geojsonl" "/work/${shp}" \
      -lco RFC7946=YES -lco ID_FIELD=ogc_fid
done

echo "→ Running tippecanoe → ne.mbtiles…"
# ghcr.io/felt/tippecanoe may be registry-restricted; fall back to indigoag/tippecanoe
# (v2.23.0) which supports --named-layer but only outputs MBTiles.
# We then convert MBTiles → PMTiles with go-pmtiles.
TIPPECANOE_IMAGE="${TIPPECANOE_IMAGE:-indigoag/tippecanoe}"
docker run --rm -v "$(pwd):/work" -w /work \
  "${TIPPECANOE_IMAGE}" \
  tippecanoe \
    -o /work/ne.mbtiles \
    --force \
    --minimum-zoom=0 --maximum-zoom=6 \
    --drop-densest-as-needed \
    --no-feature-limit --no-tile-size-limit \
    --named-layer=countries:/work/ne_50m_admin_0_countries.geojsonl \
    --named-layer=countries_lowres:/work/ne_110m_admin_0_countries.geojsonl \
    --named-layer=boundary_land:/work/ne_50m_admin_0_boundary_lines_land.geojsonl \
    --named-layer=boundary_land_lowres:/work/ne_110m_admin_0_boundary_lines_land.geojsonl \
    --named-layer=states:/work/ne_50m_admin_1_states_provinces_lines.geojsonl \
    --named-layer=ocean:/work/ne_50m_ocean.geojsonl \
    --named-layer=ocean_lowres:/work/ne_110m_ocean.geojsonl \
    --named-layer=lakes:/work/ne_50m_lakes.geojsonl \
    --named-layer=rivers:/work/ne_50m_rivers_lake_centerlines.geojsonl \
    --named-layer=coastline:/work/ne_50m_coastline.geojsonl \
    --named-layer=graticules:/work/ne_110m_graticules_10.geojsonl

echo "→ Converting ne.mbtiles → ne.pmtiles…"
docker run --rm -v "$(pwd):/work" \
  ghcr.io/protomaps/go-pmtiles:latest \
  convert /work/ne.mbtiles /work/ne.pmtiles

cp ne.pmtiles "${OUT_DIR}/ne.pmtiles"
echo "✓ Built: ${OUT_DIR}/ne.pmtiles"
ls -lh "${OUT_DIR}/ne.pmtiles"
