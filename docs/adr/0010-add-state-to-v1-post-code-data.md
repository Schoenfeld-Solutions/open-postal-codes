# ADR 0010: Add state to v1 post code data

- Date: 2026-04-30
- Status: Accepted
- Decision owner: Gabriel
- Impacts: public v1 contract, OSM extraction, local Business Central export

## Status

Accepted.

## Context

D-A-CH consumers need the first-level administrative subdivision in addition to the lower-level county or district enrichment. Germany and Austria call this value Bundesland, while Switzerland calls it canton. The local Business Central workbook also needs this subdivision for its `Bundesregion` column.

## Decision

The repository extends the v1 `post_code` schema in place with a `state` field after `country`. `state` is the stable English field name for the first-level administrative subdivision: Bundesland for Germany and Austria, canton for Switzerland. `county` remains the lower administrative subdivision when available.

The local Business Central workbook is generated from public v1 files into `tmp/private-outputs/export/`. It is a private ignored artifact, not a committed data contract and not part of GitHub Pages publication.

## Rationale

`state` is short, common in postal and business software, and maps cleanly to Business Central's regional import column. Keeping the field inside v1 avoids introducing a parallel v2 while the API is still in its foundation phase.

## Consequences

- CSV, JSON, and XML records gain the `state` field.
- Existing v1 consumers must accept the new header.
- Switzerland no longer uses canton as a `county` fallback; canton belongs in `state`.
- The Business Central workbook can combine DE, AT, and CH primary post code rows without becoming a published API artifact.

## Enforcement

- `open_postal_codes.post_code` includes `state` in serialization, dedupe identity, and place ranking keys.
- `open_postal_codes.osm_extract` enriches `state` from admin-level 4 boundaries.
- Repository checks validate the public field order across CSV, JSON, and XML.
- `open_postal_codes.business_central` validates Business Central field lengths and duplicate `(Code, Ort)` keys before writing the workbook.

## Rollout

The implementation rewrites committed regional and public files with the new v1 schema. Germany receives `state` from the existing regional source names until the next full data refresh recalculates it from OSM boundaries. Austria and Switzerland placeholders keep the new schema and are populated by the refresh workflow.
