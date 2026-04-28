# PLANS-002: Germany Post Code Extraction

This plan follows `docs/plans/PLANS.md`.

## Purpose / Big Picture

Replace the old v1 street and Liechtenstein files with a Germany-only post code API generated from regional Geofabrik PBF files.

## Progress

- [x] Define the Germany-only `post_code` public contract.
- [x] Add Python extraction, serialization, refresh, and packaging support.
- [x] Add repository checks and tests for the new API shape.
- [x] Add a dedicated data-refresh workflow for regional Geofabrik PBF files.

## Surprises & Discoveries

- Bremen address objects show that generic OSM `name` values can be POI, street, or shop names and must not be used as city fallback.
- Saarland regional extracts can include neighboring-country post code records, so spatial Germany filtering is required.
- Direct county tags were absent in the Bremen and Saarland samples, so county enrichment requires administrative boundary geometry.

## Decision Log

- v1 is replaced in place because the requested public surface is a new Germany-only contract.
- Postal-code boundaries are canonical for city names when usable.
- Address-derived city values are fallback evidence only when no usable boundary exists for the code.
- Regional PBF files are preferred over the full Germany PBF for routine automation.

## Outcomes & Retrospective

The repository now has a Germany-only post code contract, refresh automation, and tests that encode the observed Bremen and Saarland data constraints.

## Context and Orientation

Implementation entry points:

- `open_postal_codes.post_code`
- `open_postal_codes.osm_extract`
- `open_postal_codes.refresh_data`
- `.github/workflows/data-refresh.yml`
