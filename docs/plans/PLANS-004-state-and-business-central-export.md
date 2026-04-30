# PLANS-004: State Field and Business Central Export

This plan follows `docs/plans/PLANS.md`.

## Purpose / Big Picture

Publish first-level administrative subdivision data in v1 and provide a local D-A-CH Business Central workbook without making the workbook an official repository artifact.

## Progress

- [x] Add `state` to the v1 post code field order.
- [x] Enrich `state` from OSM admin-level 4 boundaries.
- [x] Keep Swiss canton data in `state` instead of duplicating it into `county`.
- [x] Add local Business Central workbook generation under ignored `tmp/` paths.
- [x] Update data files, tests, documentation, and repository checks.

## Surprises & Discoveries

- The existing Business Central workbook was already a private ignored artifact under `tmp/private-outputs/export/`.
- The template uses inline strings and can be patched with standard-library XLSX ZIP and XML handling.
- Current Germany data can receive `state` from the regional Geofabrik source files before the next full OSM refresh.

## Decision Log

- Use `state` as the English public field name for Bundesland and canton.
- Keep Business Central output unofficial and ignored.
- Map Business Central `Bundesregion` from v1 `state`, not from `county`.
- Generate only primary post code rows for the Business Central workbook.

## Outcomes & Retrospective

The v1 API publishes the additional `state` field for all D-A-CH country paths. The local Business Central generator can create `PLZ_BusinessCentral_DACH.xlsx` from public v1 data and the local template without committing workbook artifacts.

## Context and Orientation

Implementation entry points:

- `open_postal_codes.post_code`
- `open_postal_codes.osm_extract`
- `open_postal_codes.business_central`
- `docs/contracts/v1/post-code-data.md`
