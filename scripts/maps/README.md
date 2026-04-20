# Map asset pipeline

One-off scripts for building and uploading the self-hosted map tiles +
glyphs that back the explorer maps.

## Artifacts

- `ne.pmtiles` — Natural Earth 1:50m + 1:110m, zoom 0–6, ~40 MB.
  Sourced from https://naciscdn.org/naturalearth (public domain).
- `glyphs/Noto Sans Regular/<range>.pbf` — pre-built SDF glyphs from
  `protomaps/basemaps-assets` (MIT licensed).

## Build

```bash
bash scripts/maps/build_pmtiles.sh   # → build/maps/ne.pmtiles (Docker)
bash scripts/maps/fetch_glyphs.sh    # → build/maps/glyphs/Noto Sans Regular/**
```

Outputs land in `build/maps/`, which is gitignored.

## Upload to MinIO (dev)

```bash
docker compose -f docker-compose.local.yml up -d minio
bash scripts/maps/provision_bucket.sh   # one-off: creates lacos-maps bucket
bash scripts/maps/upload_assets.sh      # pushes artifacts into the bucket
```

## Upload to self-hosted S3 (prod)

Override endpoint + credentials, then run the same scripts:

```bash
export S3_ENDPOINT="https://s3.lac.example"
export S3_ACCESS_KEY="…"
export S3_SECRET_KEY="…"
bash scripts/maps/provision_bucket.sh
bash scripts/maps/upload_assets.sh
```

## Django config

Point `EXPLORER_MAP_PMTILES_URL` and `EXPLORER_MAP_GLYPHS_URL` at the
bucket. Defaults target local MinIO. See `config/settings/base.py`.
