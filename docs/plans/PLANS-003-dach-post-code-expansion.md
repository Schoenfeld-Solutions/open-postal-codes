# PLANS-003: D-A-CH Post Code Expansion

This plan follows `docs/plans/PLANS.md`.

## Purpose / Big Picture

Extend the v1 static post code API from Germany to D-A-CH while keeping the existing Germany paths stable and reusing the established ranking and evidence model.

## Progress

- [x] Choose additive v1 publication for Austria and Switzerland.
- [x] Add country-scoped configuration for validation, time zone, and Geofabrik sources.
- [x] Generalize extraction, refresh, packaging, and repository checks.
- [x] Add schema-valid public paths for `AT` and `CH`.
- [x] Update tests and documentation for D-A-CH.

## Surprises & Discoveries

- Raw PBF downloads were already protected by `.gitignore` through `*.osm.pbf` and `*.osm.pbf.part`.
- Local ignored `tmp/` content can affect repository language checks unless artifact directories are excluded by the check itself.
- Switzerland needs canton-level first-level subdivision enrichment; district values remain lower-level `county` data when available.

## Decision Log

- v1 is extended additively instead of introducing v2.
- Germany keeps regional Geofabrik downloads; Austria and Switzerland use full-country Geofabrik downloads.
- `--regions` remains a Germany-scoped smoke-run filter.
- `--countries` controls country selection for refresh runs.

## Outcomes & Retrospective

The repository supports D-A-CH public paths and refresh configuration. Austria and Switzerland start with schema-valid public placeholders and are populated by the D-A-CH refresh workflow.

## Context and Orientation

Implementation entry points:

- `open_postal_codes.countries`
- `open_postal_codes.post_code`
- `open_postal_codes.osm_extract`
- `open_postal_codes.refresh_data`
- `.github/workflows/data-refresh.yml`
