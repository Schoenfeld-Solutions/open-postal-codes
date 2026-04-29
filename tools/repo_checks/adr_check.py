"""Check foundational ADR structure."""

from __future__ import annotations

import re
from pathlib import Path

from tools.repo_checks.common import fail

REQUIRED_ADRS = (
    Path("docs/adr/0001-define-python-first-project-boundary.md"),
    Path("docs/adr/0002-define-data-layout-and-static-api.md"),
    Path("docs/adr/0003-publish-through-github-pages.md"),
    Path("docs/adr/0004-preserve-odbl-and-visible-attribution.md"),
    Path("docs/adr/0005-keep-ci-and-maintenance-low-cost.md"),
    Path("docs/adr/0006-defer-osm-extraction-dependencies.md"),
    Path("docs/adr/0007-extract-germany-post-codes-from-geofabrik-regions.md"),
    Path("docs/adr/0008-extend-v1-post-code-quality-metadata.md"),
)

REQUIRED_SECTIONS = (
    "## Status",
    "## Context",
    "## Decision",
    "## Rationale",
    "## Consequences",
    "## Enforcement",
    "## Rollout",
)

ALLOWED_STATUSES = ("Proposed", "Accepted", "Deprecated", "Superseded", "Rejected")


def main() -> int:
    errors: list[str] = []
    adr_root = Path("docs/adr")

    if not (adr_root / "README.md").exists():
        errors.append("missing docs/adr/README.md")

    for path in REQUIRED_ADRS:
        if not path.exists():
            errors.append(f"missing ADR: {path}")

    for path in sorted(adr_root.glob("[0-9][0-9][0-9][0-9]-*.md")):
        text = path.read_text(encoding="utf-8")
        if not re.match(r"^# ADR [0-9]{4}:", text):
            errors.append(f"{path}: invalid title")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                errors.append(f"{path}: missing section {section}")
        if not any(f"- Status: {status}" in text for status in ALLOWED_STATUSES):
            errors.append(f"{path}: missing allowed status metadata")

    return fail("adr-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
