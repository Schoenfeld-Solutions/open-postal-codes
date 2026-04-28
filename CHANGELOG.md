# Changelog

All notable changes to this project are documented in this file.

The format follows Keep a Changelog.

## [Unreleased]

### Added

- Python-first project foundation with package modules for post code extraction, serialization, refresh, and GitHub Pages packaging.
- Versioned `data/public/v1/` data layout and static file API.
- ADR, contract, ops, security, strategy, and plan documentation for the initialization.
- Repository checks, pytest tests, Ruff, Mypy, and coverage gates.
- GitHub Actions for pull request gates and GitHub Pages publication.
- English-only documentation policy enforcement for repository-owned text files.
- Germany-only `post_code` outputs in CSV, JSON, and XML.
- Regional Geofabrik PBF refresh workflow with no-op handling for unchanged generated outputs.
- OpenStreetMap extraction support through `osmium` and spatial enrichment through `shapely`.

### Changed

- Existing CSV files were moved from `src/` into `data/public/v1/`.
- The previous diff logic was restructured as a testable Python module.
- Azure pipeline and legacy diff workflow files were replaced with GitHub-first workflows.
- Repository documentation is now English-only.
- Pull request Dependency Review runs as a best-effort signal until Dependency graph support is enabled for the repository.
- The v1 API now publishes Germany-only `post_code` files instead of the previous German street files and Liechtenstein commune file.
- Attribution now includes Geofabrik GmbH for regional PBF source data.

### Removed

- Liechtenstein public data support.
- Previous German street-file v1 outputs and the old CSV filtering command.
