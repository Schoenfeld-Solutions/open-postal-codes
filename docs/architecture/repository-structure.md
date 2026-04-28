# Repository Structure

## Target Shape

- `src/open_postal_codes/`: Python modules for local processing and packaging.
- `data/public/v1/`: versioned data source for the static file API.
- `site/`: static HTML surface for GitHub Pages.
- `docs/`: ADRs, contracts, architecture, ops, security, strategy, and plans.
- `tests/`: unit and repository smoke tests.
- `tools/repo_checks/`: deterministic structure and governance checks.

## Principle

Code, data, and generated artifacts stay separate. `out/` is a local build result and is not versioned.
