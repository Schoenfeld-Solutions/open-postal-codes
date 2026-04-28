"""Check execution plan baseline structure."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail

REQUIRED_PLAN = Path("docs/plans/PLANS-001-initialize-repository-foundation.md")
REQUIRED_SECTIONS = (
    "## Purpose / Big Picture",
    "## Progress",
    "## Surprises & Discoveries",
    "## Decision Log",
    "## Outcomes & Retrospective",
    "## Context and Orientation",
)


def main() -> int:
    errors: list[str] = []

    if not Path("docs/plans/PLANS.md").exists():
        errors.append("missing docs/plans/PLANS.md")
    if not REQUIRED_PLAN.exists():
        errors.append(f"missing initial plan: {REQUIRED_PLAN}")

    for path in sorted(Path("docs/plans").glob("PLANS-*.md")):
        text = path.read_text(encoding="utf-8")
        if "docs/plans/PLANS.md" not in text:
            errors.append(f"{path}: missing reference to docs/plans/PLANS.md")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                errors.append(f"{path}: missing section {section}")
        progress_text = text.split("## Progress", maxsplit=1)[-1]
        if "- [" not in progress_text:
            errors.append(f"{path}: Progress requires at least one checkbox")

    return fail("plans-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
