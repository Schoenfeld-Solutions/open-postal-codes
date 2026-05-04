# Data Refresh

## Scheduled Refresh

The `Refresh D-A-CH Post Code Data` workflow runs on a schedule and by manual dispatch. It downloads D-A-CH PBF files from Geofabrik into runner-local temporary storage, extracts normalized source CSV outputs, rebuilds public CSV/JSON/XML files, and opens or updates a pull request when tracked files change. When required pull request checks pass, the workflow squash-merges the checked data commit and deletes the refresh branch.

The extraction step also recalculates location-primary markers, ranks, and evidence metadata for every public row, so committed regional CSV files must use the same schema as the public export.

The Pages manifest publishes two timestamps:

- `generated_at`: when the Pages artifact was packaged.
- `data_refreshed_at`: when the Geofabrik source metadata was refreshed.

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

## Local Business Central Export

The unofficial Business Central workbook is generated only on a maintainer workstation. It reads the public v1 CSV files, keeps only `is_primary_location=true` rows, maps the v1 `state` field into the Business Central `Bundesregion` column, and writes ignored files under `tmp/private-outputs/export/`.

```bash
python3 -m open_postal_codes.business_central --repository-root .
```

Default paths:

- Template: `tmp/private-outputs/input/PLZ.xlsx`
- Workbook: `tmp/private-outputs/export/PLZ_BusinessCentral_DACH.xlsx`
- Guardrails: `tmp/private-outputs/export/PLZ_BusinessCentral_DACH_Guardrails.md`

These files are local artifacts. They are not committed, not uploaded by Pages, and not part of the public static API contract.

## Rules

- Raw `.osm.pbf` files are never committed.
- Normalized CSV outputs under `data/regional/v1/<country>/post_code/` are committed through refresh pull requests.
- `data/sources/geofabrik-regions.json` stores remote metadata used to skip unchanged sources.
- A missing, empty, invalid, or checksum-mismatched remote file is skipped for that source, the refresh continues with the remaining sources, and the workflow fails at the end with a source summary.
- A refresh with no tracked diff is a successful no-op.
- Run the standard checks after every data refresh.

## Token Permissions

The normal pull request gates run with read-only repository permissions. The data-refresh workflow also keeps its default workflow token read-only. Data branch publication, pull request creation, required check inspection, and merge use a dedicated GitHub App installation token.

Required repository configuration:

- Variable: `DATA_REFRESH_APP_CLIENT_ID`
- Secret: `DATA_REFRESH_APP_PRIVATE_KEY`

The installed App needs only repository metadata, contents write, pull requests write, and checks read permissions. It must not need administration, Pages, secrets, or workflow permissions.

The workflow leaves the pull request open if required checks fail. Merge uses squash mode, deletes `dev/data-refresh-post-code`, and is pinned to the exact checked head commit.
