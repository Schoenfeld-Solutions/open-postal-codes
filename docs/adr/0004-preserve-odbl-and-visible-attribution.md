# ADR 0004: Preserve ODbL and visible attribution

- Date: 2026-04-28
- Status: Proposed
- Decision owner: Gabriel
- Impacts: License, README, site

## Status

Proposed.

## Context

The repository continues an existing ODbL data foundation and uses OpenStreetMap data. The license text and attribution must remain visible and traceable.

## Decision

The existing ODbL license text remains unchanged. README, NOTICE, the manifest, and the Pages site name OpenStreetMap contributors, Geofabrik GmbH, Frank Stueber, and Schoenfeld Solutions.

## Rationale

The ODbL requires clear redistribution and attribution practices. Visible notices reduce license risk and make data origin transparent.

## Consequences

- `LICENSE` is not rewritten.
- Attribution is maintained in README, NOTICE, the manifest, and the site.
- License and credit checks are part of local repository checks.

## Enforcement

- `tools.repo_checks.license_credit_check` validates license and notice files.
- `NOTICE.md` documents origin and license.
- `site/index.html` contains visible attribution.

## Rollout

The initialization adds NOTICE and site attribution without changing the ODbL text.
