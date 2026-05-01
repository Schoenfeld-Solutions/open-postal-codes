# PLANS-005: Maintainability Guardrails

This plan follows `docs/plans/PLANS.md`.

## Purpose / Big Picture

Keep Open Postal Codes easy to review as it grows by adding human-facing contribution rules and lightweight checks for module size, import boundaries, and public provenance wording.

## Progress

- [x] Add contributor documentation for module boundaries, contracts, data artifacts, and commits.
- [x] Add module-size and import-boundary repository checks.
- [x] Keep private workflow notes outside tracked public repository files.
- [x] Update README, ops docs, ADRs, tests, and repository checks.

## Surprises & Discoveries

- Current source modules already fit below stricter module-size limits.
- The repository already had a public provenance wording check, so the new rule could extend the existing check instead of introducing a separate policy.
- The existing project structure check still expected local private instruction files to be ignored; those references are no longer needed in public repository files.

## Decision Log

- Use `CONTRIBUTING.md` as the public contributor entry point.
- Keep module-size limits lower than the comparison project because this codebase is smaller.
- Keep checks standard-library only and deterministic.
- Enforce import boundaries through AST inspection instead of naming conventions alone.

## Outcomes & Retrospective

The repository now has direct guardrails against gradual monolith growth. The checks preserve current layering between domain, extraction, refresh, packaging, and private export modules without adding runtime dependencies.

## Context and Orientation

Implementation entry points:

- `CONTRIBUTING.md`
- `tools.repo_checks.module_size_check`
- `tools.repo_checks.boundary_truth_check`
- `tools.repo_checks.reference_policy_check`
