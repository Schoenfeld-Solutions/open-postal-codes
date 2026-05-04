# ADR 0013: Automate data refresh pull request merge

- Date: 2026-05-04
- Status: Accepted
- Decision owner: Gabriel
- Impacts: Data refresh, pull requests, GitHub Pages, repository operations

## Status

Accepted.

## Context

The weekly D-A-CH refresh can extract data, rebuild tracked outputs, and run quality gates, but repository policy prevents the default workflow token from creating pull requests. Pull requests created with the default workflow token also do not reliably trigger follow-up pull request checks or the Pages publication path.

## Decision

The data-refresh workflow will use a dedicated GitHub App installation token for checkout, data branch publication, pull request creation, required check inspection, and squash merge. The workflow keeps its own default token read-only and scopes the App token to repository contents, pull requests, and checks.

## Rationale

A GitHub App token is short-lived, repository-scoped, and separate from a maintainer account. It allows refresh-created pull requests to behave like normal repository pull requests while avoiding a long-lived personal token.

## Consequences

- Repository variable `DATA_REFRESH_APP_CLIENT_ID` and secret `DATA_REFRESH_APP_PRIVATE_KEY` must be configured before the scheduled refresh can publish changes.
- Data refresh pull requests use `chore(data): refresh post code outputs` so the existing title gate accepts them.
- The workflow waits for required pull request checks and merges only the exact checked head commit.
- GitHub Pages updates after the merge to `main`, and the Pages manifest exposes the source data refresh timestamp separately from the Pages artifact generation time.

## Enforcement

- `tools.repo_checks.workflow_policy_check` requires the GitHub App token flow and rejects default workflow-token pull request publication.
- The `main` ruleset continues to require pull requests, linear history, squash merge, and the repository quality checks.
- The data-refresh workflow fails and leaves the pull request open if required checks fail.

## Rollout

Merge the workflow change through a normal pull request, configure the GitHub App variable and secret, then run one manual data refresh to verify pull request creation, checks, merge, branch deletion, and Pages publication.
