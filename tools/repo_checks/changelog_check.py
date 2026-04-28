"""Check changelog governance."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail

ALLOWED_CATEGORIES = {
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
}


def unreleased_body(text: str) -> str:
    start_marker = "## [Unreleased]"
    start = text.find(start_marker)
    if start == -1:
        return ""
    body = text[start + len(start_marker) :]
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> int:
    errors: list[str] = []
    changelog = Path("CHANGELOG.md")

    if not changelog.exists():
        errors.append("missing CHANGELOG.md")
        return fail("changelog-check", errors)

    text = changelog.read_text(encoding="utf-8")
    if not text.startswith("# Changelog"):
        errors.append("CHANGELOG.md must start with '# Changelog'")
    if "Keep a Changelog" not in text:
        errors.append("CHANGELOG.md must mention Keep a Changelog")
    if "## [Unreleased]" not in text:
        errors.append("CHANGELOG.md must contain an Unreleased section")

    body = unreleased_body(text)
    if not body:
        errors.append("CHANGELOG.md must keep non-empty notes under Unreleased")

    current_category: str | None = None
    bullet_count = 0
    for line in body.splitlines():
        if line.startswith("### "):
            current_category = line.removeprefix("### ").strip()
            if current_category not in ALLOWED_CATEGORIES:
                errors.append(f"unsupported changelog category: {current_category}")
        elif line.startswith("- "):
            if current_category is None:
                errors.append("changelog bullets must be under a category")
            else:
                bullet_count += 1

    if bullet_count == 0:
        errors.append("CHANGELOG.md must contain at least one Unreleased bullet")

    return fail("changelog-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
