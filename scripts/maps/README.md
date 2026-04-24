# Map Asset Pipeline

These scripts build the self-hosted map assets used by the collection explorer maps.

The production target is not AWS S3. The intended deployment is:

1. Build the assets locally into `build/maps/`.
2. Copy them to the VM at `/opt/lacos/map-assets/`.
3. Serve them with nginx under `/map-assets/`.
4. Point Django settings at those URLs.

The MinIO/S3 helper scripts remain available for local or compatible storage experiments, but they are not the production path.

## Generated Assets

| Asset | Purpose | Output |
|---|---|---|
| `ne.pmtiles` | Natural Earth vector basemap, zoom 0 to 6 | `build/maps/ne.pmtiles` |
| `glyphs/Noto Sans Regular/*.pbf` | MapLibre label glyph ranges | `build/maps/glyphs/Noto Sans Regular/` |

`build/maps/` is gitignored. The generated files are deployment artifacts, not source files.

## Build Locally

Run from the repository root:

```bash
bash scripts/maps/build_pmtiles.sh
bash scripts/maps/fetch_glyphs.sh
du -sh build/maps build/maps/ne.pmtiles build/maps/glyphs
```

Expected total size is around 20 MB.

`build_pmtiles.sh` downloads Natural Earth shapefiles, converts them to GeoJSON sequence with GDAL, builds MBTiles with tippecanoe, then converts MBTiles to PMTiles.

`fetch_glyphs.sh` downloads prebuilt Noto Sans Regular PBF glyph ranges from `protomaps/basemaps-assets`.

## Deploy To VM

Copy the generated files to the VM:

```bash
ssh lac-prod 'mkdir -p /opt/lacos/map-assets'
scp build/maps/ne.pmtiles lac-prod:/opt/lacos/map-assets/
scp -r build/maps/glyphs lac-prod:/opt/lacos/map-assets/
```

For dev, use `lac-dev` and the same `/opt/lacos/map-assets` target.

## Nginx

The VM should serve the assets directly from disk:

```nginx
location /map-assets/ {
    alias /opt/lacos/map-assets/;
    autoindex off;

    expires 7d;
    add_header Cache-Control "public, max-age=604800";
    add_header Access-Control-Allow-Origin "*" always;

    location ~* \.pmtiles$ {
        types { application/octet-stream pmtiles; }
        add_header Accept-Ranges bytes always;
    }
}
```

The `Accept-Ranges` header is important because PMTiles reads byte ranges from the single `.pmtiles` file.

## Django Settings

Production should use:

```text
EXPLORER_MAP_PMTILES_URL=https://lacos.uni-koeln.de/map-assets/ne.pmtiles
EXPLORER_MAP_GLYPHS_URL=https://lacos.uni-koeln.de/map-assets/glyphs
EXPLORER_MAIN_MAP_STYLE_URL=/maps/style/natural-earth-c.json
EXPLORER_MAIN_MAP_DARK_STYLE_URL=/maps/style/natural-earth-c.json
```

Dev should use:

```text
EXPLORER_MAP_PMTILES_URL=https://dev.lacos.uni-koeln.de/map-assets/ne.pmtiles
EXPLORER_MAP_GLYPHS_URL=https://dev.lacos.uni-koeln.de/map-assets/glyphs
EXPLORER_MAIN_MAP_STYLE_URL=/maps/style/natural-earth-c.json
EXPLORER_MAIN_MAP_DARK_STYLE_URL=/maps/style/natural-earth-c.json
```

The style endpoint stays inside Django so `map_style_view` can replace placeholders in `lacos/static/vendor/maps/lac/natural-earth-c.json` at request time.

## Local MinIO Helper Scripts

`provision_bucket.sh` and `upload_assets.sh` can publish `build/maps/` to a MinIO or S3-compatible endpoint. This is useful when testing the old local default URLs:

```text
http://localhost:9100/lacos-maps/ne.pmtiles
http://localhost:9100/lacos-maps/glyphs
```

Do not describe these helper scripts as the production deployment path. Production map assets are server-hosted on the VM through nginx.

## Verification

```bash
curl -I https://lacos.uni-koeln.de/map-assets/ne.pmtiles
curl -I "https://lacos.uni-koeln.de/map-assets/glyphs/Noto%20Sans%20Regular/0-255.pbf"
```

Then open the collection explorer and check the browser network tab. Map-related requests should go only to LACOS controlled hosts, not to Google Maps, Mapbox, OpenStreetMap tile servers, OpenFreeMap, or MapLibre demo tiles.
