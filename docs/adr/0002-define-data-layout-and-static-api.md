# ADR 0002: Define the data layout and static API

- Date: 2026-04-28
- Status: Proposed
- Decision owner: Gabriel
- Impacts: Data, API, GitHub Pages

## Status

Proposed.

## Context

The data should be directly and cheaply accessible. A dynamic service would add unnecessary cost and operational complexity for static file delivery.

## Decision

The repository uses `data/public/v1/` as the canonical source for published files. GitHub Pages serves these files as a static file API under `/open-postal-codes/api/v1/`.

## Rationale

Static files are cacheable, auditable, and do not require ongoing server costs. The `index.json` manifest makes file paths, hashes, sizes, media types, and record counts machine-readable.

## Consequences

- API versioning uses path segments such as `v1`.
- `.gz` downloads are generated in the Pages artifact but are not versioned.
- Breaking changes to public fields, titles, or file paths require a new contract version.

## Enforcement

- `open_postal_codes.pages` packages the API.
- `tools.repo_checks.pages_contract_check` validates source paths and post code formats.
- `docs/contracts/v1/` documents post code and API contracts.

## Rollout

The active v1 publication creates `api/v1/index.json` and copies D-A-CH post code CSV, JSON, and XML files into the Pages artifact.
