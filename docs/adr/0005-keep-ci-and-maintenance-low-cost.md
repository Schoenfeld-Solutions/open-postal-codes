# ADR 0005: Keep CI and maintenance low-cost

- Date: 2026-04-28
- Status: Proposed
- Decision owner: Gabriel
- Impacts: CI, dependencies, maintenance

## Status

Proposed.

## Context

The CSV files are large, but this initialization does not require expensive data downloads or long extraction jobs. Automated maintenance should be useful without creating excessive pull request or CI churn.

## Decision

Pull request CI runs only fast Python, test, coverage, and repository checks. Dependabot groups `pip` and `github-actions` updates weekly with at most one open maintenance pull request.

## Rationale

Fast deterministic checks provide early feedback and keep CI costs low. Grouped updates reduce review effort.

## Consequences

- No OpenStreetMap downloads run in pull request CI.
- No Pages deployments run for pull requests.
- Security updates remain separately visible.

## Enforcement

- `.github/dependabot.yml` defines weekly grouped updates.
- The pull request workflow installs only development dependencies and runs local gates.
- The Pages workflow runs only for `main` or manual dispatch.

## Rollout

Legacy workflows are replaced by two focused GitHub workflows.
