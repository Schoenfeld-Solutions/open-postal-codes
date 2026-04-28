# ADR 0003: Publish through GitHub Pages

- Date: 2026-04-28
- Status: Proposed
- Decision owner: Gabriel
- Impacts: CI, hosting, operations

## Status

Proposed.

## Context

The project needs public delivery for CSV files and metadata. The previous Azure mirror path no longer matches the desired GitHub-first operation model.

## Decision

GitHub Actions and GitHub Pages are the only planned publication path. Pull requests do not run Pages deployments. Deployments run only after pushes to `main` or manual dispatch.

## Rationale

This reduces cost, permissions, and operational surface area. The data is static and does not need a second hosting stack.

## Consequences

- `azure-pipelines.yml` is removed.
- Pages deployment uses minimal permissions.
- Pull requests validate quality but do not create public previews.

## Enforcement

- `.github/workflows/pages.yml` builds and deploys the Pages artifact.
- `.github/workflows/pull-request.yml` validates pull requests without deployment.
- Repository checks prevent reintroducing legacy pipeline files.

## Rollout

After a merge to `main`, the Pages workflow creates the static artifact from `site/` and `data/public/v1/`.
