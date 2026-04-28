# PLANS-001: Initialize the repository foundation

This plan follows `docs/plans/PLANS.md`.

## Purpose / Big Picture

The existing data repository is initialized as a GitHub Pages and CI-first Python project. The goal is a clear foundation for data, Python code, the static API, documentation, tests, and low-cost automation without changing the existing extraction algorithm behavior.

## Progress

- [x] Existing data paths analyzed.
- [x] Target structure for data, code, docs, tests, and workflows defined.
- [x] CSV files moved into `data/public/v1/`.
- [x] Python package, site packaging, repository checks, and tests added.
- [x] ADRs, contracts, ops documents, and GitHub workflows added.
- [x] Repository-owned documentation converted to English-only.

## Surprises & Discoveries

- The German street dataset is large enough that pull request CI should not run re-extraction or download jobs.
- The old Azure pipeline was only a mirror path and does not fit the GitHub-first target structure.

## Decision Log

- GitHub Pages is used as a static file API.
- `data/public/v1/` is the canonical data source for v1.
- Runtime dependencies remain empty for the initialization.
- ODbL and visible attribution are maintained in README, NOTICE, and the site.
- Repository-owned documentation is English-only.

## Outcomes & Retrospective

The initialization is complete when standard checks, repository checks, and Pages packaging run locally and the new structure contains no legacy pipeline files.

## Context and Orientation

Read first:

- `README.md`
- `docs/adr/README.md`
- `docs/contracts/README.md`
- `docs/ops/development-checks.md`
- `docs/security/data-handling.md`

Do not change without a dedicated decision:

- ODbL license text in `LICENSE`
- CSV headers in `data/public/v1/**`
- new production dependencies for OpenStreetMap extraction
