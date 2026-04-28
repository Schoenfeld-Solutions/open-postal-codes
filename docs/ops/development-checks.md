# Development Checks

## Standard Run

```bash
python3 -m pytest --cov=open_postal_codes --cov-fail-under=85
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy src tests tools
python3 -m tools.repo_checks.all_checks
```

## Optional Local Hooks

```bash
python3 -m pip install -e '.[dev]'
pre-commit install
pre-commit install --hook-type pre-push
```

## Goal

The checks protect post code contracts, API packaging, credits, structure, documentation baseline, Python style, types, coverage, and the English-only repository text policy.

## Pull Request Dependency Review

The pull request workflow runs GitHub Dependency Review as a best-effort supply-chain signal. Python quality gates remain blocking. Dependency Review should become a blocking gate after the repository has Dependency graph support enabled.
