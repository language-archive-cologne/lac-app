# Language Archive Cologne

## ACL access levels

The ACL system exposes three access levels derived from `acl.json` rules:

- `public`: `foaf:Agent` with `acl:Read` (anyone can read)
- `academic`: `acl:AuthenticatedAgent` with `acl:Read` (signed-in users can read)
- `restricted`: specific agents/groups with `acl:Read` or no readable entries

Legacy ACL values are mapped as follows:

- `protected` -> `academic`
- `embargo` -> `restricted`

Archivist access:

- Users in the `archivists` Django group (or superusers) can access storage
  management UI endpoints and bypass ACL read checks.

## Collection update workflow

The importers now support an update mode that refreshes existing collections/bundles
instead of returning early. Update mode is opt-in and clears related M2M links before
re-importing metadata to avoid duplicates.

### Reindex command (recommended)

Run the reindex command in the Django container to update collections (and optionally
their bundles) from the latest S3 XML:

```bash
docker compose -f docker-compose.local.yml run --rm django \
  python manage.py reindex_collection --identifier <md_self_link>
```

Useful flags:
- `--update-bundles` reindexes bundle XMLs linked to the collection
- `--prefix <s3-prefix>` scans a prefix and reindexes found XMLs
- `--all` reindexes every collection with an `import_object_key`
- `--dry-run` prints what would be reindexed without changes
- `--bucket <bucket>` overrides the configured bucket

### Ingest task update mode

The ingest tasks accept `update_existing=True` to enable in-place updates:

```python
import_s3_collection(bucket, s3_key, update_existing=True)
import_s3_bundle(bucket, s3_key, update_existing=True)
process_s3_prefix(bucket, prefix, update_existing=True)
```
