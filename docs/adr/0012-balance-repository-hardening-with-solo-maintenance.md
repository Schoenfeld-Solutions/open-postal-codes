# ADR 0012: Balance repository hardening with solo maintenance

- Date: 2026-05-02
- Status: Accepted
- Decision owner: Gabriel
- Impacts: CI, tests, repository checks, maintainability

## Status

Accepted.

## Context

The repository already has D-A-CH data, public contracts, scheduled refresh automation, and contributor-facing maintainability rules. The next quality step should improve confidence without adding paid services, heavy review process, or enterprise-only operations.

## Decision

Repository hardening will use local Python checks, free GitHub workflow features, targeted tests, and concise maintainer documentation. Public API paths and fields remain unchanged.

## Rationale

The repository is small enough to stay understandable with strict module boundaries, data-quality checks, and a fast test suite. Higher confidence should come from sharper local gates rather than external services.

## Consequences

- Coverage gates move to 90 percent after targeted tests are added.
- Public data quality gets an explicit repository check.
- CI adds timeouts, Pages packaging, and whitespace checks without new services.
- Module-size limits become stricter to slow gradual drift.

## Enforcement

- `tools.repo_checks.all_checks` includes public data quality, module size, boundary, contract, language, and reference checks.
- Pull request, Pages, and refresh workflows run the same core gates.
- `docs/ops/maintainer-scorecard.md` records the recurring solo-maintainer review checklist.

## Rollout

Apply the hardening in one focused pull request, then keep future changes within the tightened gates.
