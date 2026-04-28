# ADR 0005: Keep CI and maintenance low-cost

- Date: 2026-04-28
- Status: Proposed
- Decision owner: Gabriel
- Impacts: CI, dependencies, maintenance

## Status

Proposed.

## Context

OpenStreetMap regional PBF files can be large. Automated maintenance should be useful without creating excessive pull request or CI churn.

## Decision

Pull request CI runs only fast Python, test, coverage, and repository checks. A dedicated data-refresh workflow downloads regional Geofabrik PBF files on schedule or manual dispatch. Dependabot groups `pip` and `github-actions` updates weekly with at most one open maintenance pull request.

## Rationale

Fast deterministic checks provide early feedback and keep CI costs low. Grouped updates reduce review effort.

## Consequences

- No OpenStreetMap downloads run in pull request CI.
- Regional OpenStreetMap downloads run only in the data-refresh workflow.
- No Pages deployments run for pull requests.
- Security updates remain separately visible.
- Dependency Review remains visible in pull request CI and is treated as best-effort until Dependency graph support is enabled for the repository.

## Enforcement

- `.github/dependabot.yml` defines weekly grouped updates.
- The pull request workflow installs only development dependencies and runs local gates as blocking checks.
- The data-refresh workflow downloads PBF files into runner-local temporary storage and opens a pull request only when tracked files change.
- Dependency Review should be made blocking after the repository supports the feature.
- The Pages workflow runs only for `main` or manual dispatch.

## Rollout

Legacy workflows are replaced by two focused GitHub workflows.
