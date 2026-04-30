# ADR 0007: Extract Germany post codes from Geofabrik regions

- Date: 2026-04-28
- Status: Accepted
- Decision owner: Gabriel
- Impacts: OpenStreetMap, Geofabrik, dependencies, data refresh

## Status

Accepted. ADR 0009 extends the publication scope from Germany to D-A-CH.

## Context

This decision introduced Germany post code extraction. The full Germany PBF is large, while Geofabrik publishes smaller regional Germany PBF files that allow scoped retries and lower routine refresh cost.

## Decision

The repository uses regional Geofabrik Germany PBF files as the Germany data-refresh source. Python extracts post code records with `osmium`, enriches and filters spatial data with `shapely`, writes normalized regional CSV outputs, and builds public CSV, JSON, and XML files.

## Rationale

Regional refreshes avoid routine full-country downloads, keep failures localized, and let unchanged regions be skipped through tracked source metadata. `osmium` provides streaming PBF processing and `shapely` provides the spatial operations required for country filtering and administrative-boundary enrichment.

## Consequences

- Runtime dependencies include `osmium` and `shapely`.
- Pull request CI stays fast and does not download PBF files.
- The data-refresh workflow can fail on unavailable, empty, invalid, or checksum-mismatched source files.
- A refresh with no tracked diff is a successful no-op.

## Enforcement

- `open_postal_codes.refresh_data` performs metadata checks, download validation, extraction, merge, and public file generation.
- `open_postal_codes.osm_extract` implements boundary-canonical post code extraction and spatial filtering.
- Repository checks require the configured public v1 post code files and Geofabrik attribution.

## Rollout

The old street and Liechtenstein public files are removed from v1. The first committed post code files are seeded from the existing German data, and subsequent refresh pull requests replace them from Geofabrik regional PBF extraction.
