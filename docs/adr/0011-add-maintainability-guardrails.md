# ADR 0011: Add maintainability guardrails

- Date: 2026-05-01
- Status: Accepted
- Decision owner: Gabriel
- Impacts: repository checks, contributor documentation, CI gates

## Status

Accepted.

## Context

The repository now contains enough production code, generated data, contracts, and private export tooling that gradual growth needs explicit safeguards. The goal is to keep the project readable as a public Python data repository without adding process-heavy tooling or new runtime dependencies.

## Decision

The repository adds contributor-facing maintainability rules and deterministic checks for module size, import boundaries, and public provenance wording.

`CONTRIBUTING.md` is the public entry point for contributor rules. Private, tool-specific workflow notes are not part of the tracked repository contract.

## Rationale

Line-count and import-boundary checks catch drift before modules turn into mixed-purpose files. Public contributor documentation is easier to review and more appropriate for a public project than tool-specific local notes.

## Consequences

- `tools.repo_checks.all_checks` includes module-size and import-boundary checks.
- Public repository text is checked for prohibited provenance wording.
- Future modules should be split before they mix parsing, orchestration, validation, and output generation.
- Any change to these guardrails should update the README, development checks, and this ADR family.

## Enforcement

- `module_size_check` blocks oversized source, test, and repository-check modules.
- `boundary_truth_check` blocks imports that cross the documented runtime boundaries.
- `reference_policy_check` blocks prohibited provenance wording in public tracked text.
- `project_structure_check` requires the contributor guide and guardrail files.

## Rollout

The checks are introduced while all current modules fit the configured limits. Pull request and Pages workflows already call `tools.repo_checks.all_checks`, so the new guardrails become part of the existing quality gates without additional workflow changes.
