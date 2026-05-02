# Repository Structure

## Target Shape

- `src/open_postal_codes/`: Python modules for local processing and packaging.
- `data/public/v1/`: versioned data source for the static file API.
- `data/regional/v1/<country>/post_code/`: normalized source post code CSV outputs created by refresh pull requests.
- `data/sources/`: source metadata used to skip unchanged Geofabrik regional files.
- `site/`: static HTML surface for GitHub Pages.
- `docs/`: ADRs, contracts, architecture, ops, security, strategy, and plans.
- `tests/`: unit and repository smoke tests.
- `tools/repo_checks/`: deterministic structure and governance checks.
- `CONTRIBUTING.md`: public contributor rules for maintainability, contracts, data artifacts, and commits.

## Principle

Code, tracked data, source metadata, and generated artifacts stay separate. `out/` and downloaded PBF files are local build results and are not versioned.

Runtime modules stay small and layered. Domain rules, country configuration, OSM enrichment, OSM extraction, refresh orchestration, Pages packaging, and private exports remain separate responsibilities.
