# PLANS-007: Refresh progress logging

This plan follows `docs/plans/PLANS.md`.

## Purpose / Big Picture

Make long scheduled Geofabrik refresh runs observable while keeping the refresh workflow small, sequential, and compatible with the existing D-A-CH data contract.

## Progress

- [x] Add optional per-source progress callbacks to the refresh orchestration path.
- [x] Enable flushed CLI progress output for GitHub Actions runs.
- [x] Add workflow-policy coverage for unbuffered refresh execution.
- [x] Document refresh progress behavior for maintainers.

## Surprises & Discoveries

- The previous long workflow step could spend more than an hour in refresh execution without visible per-source progress.
- The refresh command already has enough source and country context to produce useful human-readable progress without a separate logging framework.

## Decision Log

- Keep progress output as maintainer observability, not a stable public contract.
- Keep direct `refresh_data(...)` library calls quiet unless a progress callback is provided.
- Use unbuffered Python execution in the workflow so progress reaches GitHub Actions promptly.
- Validate the live behavior with a scoped `countries=de`, `regions=bremen` workflow run instead of another full D-A-CH refresh.

## Outcomes & Retrospective

Refresh runs now report source selection, per-source metadata checks, skip/download/extract outcomes, failures, and public output rebuild counts. This closes the immediate observability gap without adding dependencies or changing public API files.

## Context and Orientation

Relevant entry points:

- `src/open_postal_codes/refresh_data.py`
- `.github/workflows/data-refresh.yml`
- `tools/repo_checks/workflow_policy_check.py`
- `docs/ops/data-refresh.md`
