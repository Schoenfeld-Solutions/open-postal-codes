# Release Readiness

This checklist is the release gate for a solo-maintained repository. It keeps public contracts, data artifacts, workflow behavior, and rollback paths reviewable without adding paid services.

## Local Gates

Run the full local gate before opening or merging a pull request:

```bash
python3 -m pytest --cov=open_postal_codes --cov-fail-under=90
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy src tests tools
python3 -m tools.repo_checks.all_checks
python3 -m open_postal_codes.pages --output-root out
git diff --check
git ls-files '*.osm.pbf' '*.osm.pbf.part'
```

The expected PBF listing is empty.

## Data Readiness

`tools.repo_checks.all_checks` verifies the public D-A-CH data contract and collapse guards:

- all nine public v1 files exist under `data/public/v1/{de,at,ch}/`
- every D-A-CH row has a non-empty `state`
- country record floors and unique post-code floors remain above conservative minimums
- sentinel rows for Bremen, Wien, and Zürich include the expected country, state, and time zone
- Geofabrik metadata has expected keys, URLs, positive content lengths, MD5 values, and non-empty remote metadata when present
- raw PBF downloads are not tracked

## Pages Readiness

The Pages artifact check packages the site into a temporary directory and verifies:

- `index.html` and `404.html`
- `api/v1/index.json`
- all nine CSV, JSON, and XML files
- all generated `.gz` files
- manifest media types, URLs, byte counts, record counts, and SHA-256 hashes
- gzip files decompress to the original API files

The generated `out/` directory remains a local artifact and is not committed.

## Workflow Readiness

The workflow policy check keeps GitHub Actions predictable and low-cost:

- every workflow has explicit `permissions`, `concurrency`, and job `timeout-minutes`
- pull request CI runs tests, Ruff, format check, Mypy, repository checks, Pages packaging, and whitespace checks
- pull request CI does not download live PBF files
- data refresh remains weekly and keeps write permissions scoped to data pull requests
- Pages deployment is separated from data refresh

## Merge Flow

1. Create a short-lived `dev/` branch from synced `main`.
2. Keep commits focused and use Conventional Commit subjects.
3. Open a pull request against `main` with summary, risk, rollback, and validation evidence.
4. Wait for all required checks to pass.
5. Squash merge with a valid Conventional Commit subject.
6. Delete the remote feature branch.
7. Switch back to `main`, fetch, fast-forward pull, and delete the local feature branch.
8. Confirm `git status --short --branch` shows a clean `main`.

## Rollback

- For code, docs, or workflow regressions, revert the squash commit in a new pull request.
- For data regressions, revert the data refresh pull request or run a corrected refresh from the last good `main`.
- For Pages deployment issues, use the last green `main` commit as the known-good source and keep generated artifacts out of Git history.

## Private Outputs

The Business Central workbook is a local private artifact under `tmp/private-outputs/export/`. It is not part of the public contract, not published through Pages, and not committed.
