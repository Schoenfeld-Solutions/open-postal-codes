# Static API

## Flow

1. `site/` is copied into the Pages artifact.
2. `data/public/v1/` is copied into the artifact under `api/v1/`.
3. A `.gz` file is created for every public data file.
4. `api/v1/index.json` is calculated from the copied files.

## Properties

- no dynamic endpoints
- no server-side state
- reproducible file paths
- metadata for hashes and sizes in the manifest
