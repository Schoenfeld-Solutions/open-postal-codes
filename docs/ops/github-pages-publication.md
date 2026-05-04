# GitHub Pages Publication

## Triggers

The Pages workflow runs after a push to `main` or through `workflow_dispatch`.

## Flow

1. Check out the repository.
2. Set up Python `3.12`.
3. Run development gates.
4. Run `python3 -m open_postal_codes.pages --output-root out`.
5. Upload `out/` as the GitHub Pages artifact.
6. Deploy GitHub Pages.

The Pages workflow publishes committed public data only. It does not download Geofabrik PBF files or run data extraction.

The manifest includes `generated_at` for the Pages artifact build and `data_refreshed_at` for the source metadata refresh that produced the committed data. The portal displays the data refresh timestamp when it is available.

## Permissions

The deploy job needs only `contents: read`, `pages: write`, and `id-token: write`.
