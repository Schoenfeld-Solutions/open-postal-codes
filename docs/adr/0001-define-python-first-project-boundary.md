# ADR 0001: Define the Python-first project boundary

- Date: 2026-04-28
- Status: Proposed
- Decision owner: Gabriel
- Impacts: Repository, code, data, documentation

## Status

Proposed. This decision describes the initial target structure.

## Context

The repository previously contained data, a small Python script, and legacy publication automation in a flat structure. Ongoing maintenance needs clear boundaries between code, published data, documentation, and generated artifacts.

## Decision

The repository is maintained as a Python-first data project. Production Python code lives under `src/open_postal_codes/`. Published CSV data lives under `data/public/v1/`. GitHub Pages artifacts are built from these sources and remain unversioned.

## Rationale

A `src` layout reduces implicit import paths and keeps code testable. Data under `data/public/v1/` can serve as the stable versioned API source without being mixed into Python modules.

## Consequences

- `src/` contains Python code only.
- CSV files are part of the versioned data surface, not part of the code package.
- New runtime languages or production roots require a new ADR.

## Enforcement

- `pyproject.toml` defines the Python package.
- Repository checks validate the target structure.
- Tests validate the curated public surface.

## Rollout

The existing CSV files are moved into `data/public/v1/` with history-preserving Git moves.
