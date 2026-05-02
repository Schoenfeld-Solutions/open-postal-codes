# PLANS-006: Balanced repository hardening

This plan follows `docs/plans/PLANS.md`.

## Purpose / Big Picture

Raise repository confidence for a public solo-maintained D-A-CH data project without changing the v1 API, adding paid services, or introducing production dependencies.

## Progress

- [x] Split pure OSM enrichment logic out of extraction orchestration.
- [x] Split oversized unit test files by behavior area.
- [x] Add public data-quality checks for D-A-CH files, metadata, states, floors, sentinels, and tracked PBF files.
- [x] Raise coverage gates to 90 percent.
- [x] Add free CI polish, maintainer documentation, and security reporting guidance.

## Surprises & Discoveries

- The existing suite was fast and green, but `business_central.py` and OSM enrichment paths had the most useful uncovered branches.
- Public data had non-empty `state` values across DE, AT, and CH, making a state completeness guard practical.

## Decision Log

- Keep the public v1 schema and paths unchanged.
- Use conservative record floors as collapse guards, not exact expected counts.
- Keep refresh downloads out of pull request CI.
- Prefer local repository checks over external quality services.

## Outcomes & Retrospective

The hardening keeps the project small while adding stronger evidence for public data quality, module cohesion, and operational repeatability.

## Context and Orientation

Relevant entry points:

- `src/open_postal_codes/osm_extract.py`
- `src/open_postal_codes/osm_enrichment.py`
- `tools/repo_checks/public_data_quality_check.py`
- `docs/ops/maintainer-scorecard.md`
