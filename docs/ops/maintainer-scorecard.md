# Maintainer Scorecard

This checklist keeps the repository reviewable as a solo-maintained public data project.

## Release Readiness

- Standard checks pass locally and in pull request CI.
- Public data files match the v1 contract and pass data-quality guardrails.
- Pages packaging succeeds and produces the expected nine API files.
- No raw PBF files, local exports, logs, or build artifacts are tracked.
- Contract, ops, ADR, plan, and changelog updates match any behavior changes.

## Data Refresh Readiness

- Scheduled refresh remains weekly.
- Refresh pull requests include source scope, changed files, and passing gates.
- Source metadata contains all D-A-CH Geofabrik keys.
- Data floors remain conservative collapse guards, not exact record expectations.

## Maintainability Readiness

- Runtime modules stay below the product line limit.
- Tests stay focused by behavior area and below the test line limit.
- Domain, extraction, refresh, Pages packaging, and private export code remain separated.
- New dependencies are avoided unless the repository has a documented reason and tests.
