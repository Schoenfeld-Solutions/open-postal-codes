# ADR 0006: Defer OpenStreetMap extraction dependencies

- Date: 2026-04-28
- Status: Proposed
- Decision owner: Gabriel
- Impacts: OpenStreetMap, dependencies, extraction

## Status

Proposed.

## Context

A full extraction from OpenStreetMap PBF files is more compute- and data-intensive than the current structure initialization. Specialized libraries are still likely to be appropriate for a robust later implementation.

## Decision

The initialization does not add runtime dependencies for OpenStreetMap extraction. For a later extraction workstream, `osmium/pyosmium` remains the preferred candidate for PBF streaming and `shapely` remains the preferred candidate for geometry and spatial-index work.

## Rationale

The current scope is structure, packaging, and governance. New production dependencies should be introduced only with a concrete extraction design, tests, and cost review.

## Consequences

- `pyproject.toml` starts without runtime dependencies.
- OpenStreetMap extraction remains follow-up work.
- New dependencies require explicit approval and documented tests.

## Enforcement

- Repository checks do not expect an OpenStreetMap runtime dependency.
- README describes extraction as outside the initialization scope.
- Follow-up plans must be specific to this repository.

## Rollout

There is no migration in this initialization. A later extraction implementation receives its own ADR and plan.
