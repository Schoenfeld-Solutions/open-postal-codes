# Development Checks

## Standard Run

```bash
python3 -m pytest --cov=open_postal_codes --cov-fail-under=90
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy src tests tools
python3 -m tools.repo_checks.all_checks
python3 -m open_postal_codes.pages --output-root out
git diff --check
```

## Optional Local Hooks

```bash
python3 -m pip install -e '.[dev]'
pre-commit install
pre-commit install --hook-type pre-push
```

## Goal

The checks protect post code contracts, API packaging, credits, structure, documentation baseline, Python style, types, coverage, and the English-only repository text policy.

`tools.repo_checks.all_checks` also protects maintainability boundaries:

- source, test, and repository-check modules have line-count limits
- domain code is kept separate from extraction, network refresh, Pages packaging, and private export code
- public D-A-CH data files, metadata values, state completeness, record floors, unique post-code floors, sentinel rows, and tracked PBF files are checked
- Pages artifacts are packaged into a temporary directory and checked for manifest, gzip, hash, record-count, and static-file consistency
- GitHub workflows are checked for explicit permissions, concurrency, timeouts, weekly refresh cadence, and pull request gates without live PBF downloads
- every third-party GitHub Action is pinned to an immutable 40-character commit SHA with a readable release-version comment; floating version tags are rejected
- the data-refresh workflow is checked for code-first preflight ordering, main-only opt-in publication, serialized runs, bounded pull request waiting, always-on JSON diagnostics, and the absence of PBF matrices or caches
- tracked public text is checked for prohibited provenance wording

Pull request CI also packages the Pages artifact and runs `git diff --check`.

The scheduled refresh splits the same controls into two phases. Unit, Ruff, format, and Mypy
checks run before any PBF download. Repository data checks, Pages packaging, and the final
`git diff --check` run only after candidate data has been generated, allowing a refresh to
repair a previously invalid committed dataset while still validating the final output.

## Pull Request Dependency Review

The pull request workflow runs GitHub Dependency Review as a best-effort supply-chain signal. Python quality gates remain blocking. Dependency Review should become a blocking gate after the repository has Dependency graph support enabled.
