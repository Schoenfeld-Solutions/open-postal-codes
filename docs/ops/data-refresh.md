# Data Refresh

## Scheduled Refresh

The `Refresh D-A-CH Post Code Data` workflow runs on a schedule and by manual dispatch. It downloads D-A-CH PBF files from Geofabrik into runner-local temporary storage, extracts normalized source CSV outputs, rebuilds public CSV/JSON/XML files, and opens or updates a pull request when tracked files change.

The extraction step also recalculates location-primary markers, ranks, and evidence metadata for every public row, so committed regional CSV files must use the same schema as the public export.

## Manual Scoped Run

```bash
python3 -m open_postal_codes.refresh_data \
  --download-root /tmp/open-postal-codes-pbf \
  --countries de \
  --regions bremen
```

Refresh only Austria and Switzerland:

```bash
python3 -m open_postal_codes.refresh_data \
  --download-root /tmp/open-postal-codes-pbf \
  --countries at,ch
```

## Rules

- Raw `.osm.pbf` files are never committed.
- Normalized CSV outputs under `data/regional/v1/<country>/post_code/` are committed through refresh pull requests.
- `data/sources/geofabrik-regions.json` stores remote metadata used to skip unchanged sources.
- A missing, empty, invalid, or checksum-mismatched remote file is skipped for that source, the refresh continues with the remaining sources, and the workflow fails at the end with a source summary.
- A refresh with no tracked diff is a successful no-op.
- Run the standard checks after every data refresh.

## Token Permissions

The normal pull request gates run with read-only repository permissions. The data-refresh workflow is the only workflow that requests `contents: write` and `pull-requests: write`; those permissions are limited to committing generated data on `dev/data-refresh-post-code` and opening or updating the corresponding pull request. If repository or organization policy prevents write permissions for workflow tokens, the refresh can still validate extraction locally in the runner, but pull request publication must be handled with an approved token or manually from a maintainer workstation.
