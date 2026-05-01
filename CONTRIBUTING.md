# Contributing

Open Postal Codes is a small public data repository. Changes should keep the project easy to audit, reproduce, and operate.

## Development Baseline

Use Python `3.12` or newer and install the local development dependencies:

```bash
python3 -m pip install -e '.[dev]'
```

Run the standard checks before opening a pull request:

```bash
python3 -m pytest --cov=open_postal_codes --cov-fail-under=85
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy src tests tools
python3 -m tools.repo_checks.all_checks
```

## Module Boundaries

- Keep modules focused on one responsibility.
- Keep shared country and validation rules in `countries.py` and `post_code.py`.
- Keep OSM extraction, data refresh, Pages packaging, and private export generation separate.
- Do not introduce cyclic imports between runtime modules.
- Split a module before it grows into mixed orchestration, parsing, validation, and output code.

## Public Contracts

- Public CSV, JSON, XML, path, field-order, and manifest changes require matching contract documentation and tests.
- Backward-compatible expansion is preferred over replacement.
- Breaking public API changes require an ADR before implementation.

## Data and Local Artifacts

- Raw `.osm.pbf` downloads stay outside the repository.
- Generated Pages output stays under `out/`.
- Private workbook exports stay under `tmp/private-outputs/`.
- Versioned data under `data/public/`, `data/regional/`, and `data/sources/` should change only through explicit data-refresh or contract work.

## Commits and Reviews

- Use Conventional Commit titles.
- Keep commits focused on one coherent change.
- Update README, contracts, ops docs, plans, ADRs, and changelog entries when behavior or public interfaces change.
- Keep repository text English-only.
