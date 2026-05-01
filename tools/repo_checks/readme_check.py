"""Check the README entrypoint."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail

REQUIRED_SECTIONS = (
    "# Open Postal Codes",
    "## Datasets",
    "## Static File API",
    "## Installation and Development",
    "## Data Maintenance",
    "## Attribution and License",
)

REQUIRED_SNIPPETS = (
    "data/public/v1/at/post_code.csv",
    "data/public/v1/ch/post_code.csv",
    "data/public/v1/de/post_code.csv",
    "data/public/v1/de/post_code.json",
    "data/public/v1/de/post_code.xml",
    "CONTRIBUTING.md",
    "python3 -m pytest --cov=open_postal_codes --cov-fail-under=85",
    "python3 -m ruff check .",
    "python3 -m ruff format --check .",
    "python3 -m mypy src tests tools",
    "python3 -m tools.repo_checks.all_checks",
    "code,city,country,state,county,time_zone,"
    "is_primary_location,location_rank,postal_code_rank,source,evidence_count",
    "is_primary_location",
    "location_rank",
    "postal_code_rank",
    "evidence_count",
    "/open-postal-codes/api/v1/index.json",
    "/open-postal-codes/api/v1/at/post_code.csv",
    "/open-postal-codes/api/v1/ch/post_code.csv",
    "/open-postal-codes/api/v1/de/post_code.csv",
    "ODbL",
    "OpenStreetMap",
    "Geofabrik GmbH",
    "Frank Stueber",
)


def main() -> int:
    errors: list[str] = []
    readme = Path("README.md")

    if not readme.exists():
        errors.append("missing README.md")
        return fail("readme-check", errors)

    text = readme.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"README missing section: {section}")
    for snippet in REQUIRED_SNIPPETS:
        if snippet not in text:
            errors.append(f"README missing required snippet: {snippet}")

    return fail("readme-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
