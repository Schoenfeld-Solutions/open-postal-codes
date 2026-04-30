"""Check foundational repository paths."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail

REQUIRED_DIRECTORIES = (
    Path(".github/workflows"),
    Path("data/public/v1/at"),
    Path("data/public/v1/ch"),
    Path("data/public/v1/de"),
    Path("data/regional/v1/at/post_code"),
    Path("data/regional/v1/ch/post_code"),
    Path("data/regional/v1/de/post_code"),
    Path("data/sources"),
    Path("docs/adr"),
    Path("docs/architecture"),
    Path("docs/contracts/v1"),
    Path("docs/ops"),
    Path("docs/plans"),
    Path("docs/security"),
    Path("docs/strategy"),
    Path("site"),
    Path("src/open_postal_codes"),
    Path("tests/fixtures"),
    Path("tests/repo_smoke"),
    Path("tests/unit"),
    Path("tools/repo_checks"),
)

REQUIRED_FILES = (
    Path(".gitattributes"),
    Path(".github/dependabot.yml"),
    Path(".github/workflows/data-refresh.yml"),
    Path(".github/workflows/pages.yml"),
    Path(".github/workflows/pull-request.yml"),
    Path(".gitignore"),
    Path(".pre-commit-config.yaml"),
    Path("CHANGELOG.md"),
    Path("LICENSE"),
    Path("NOTICE.md"),
    Path("README.md"),
    Path("data/public/v1/at/post_code.csv"),
    Path("data/public/v1/at/post_code.json"),
    Path("data/public/v1/at/post_code.xml"),
    Path("data/public/v1/ch/post_code.csv"),
    Path("data/public/v1/ch/post_code.json"),
    Path("data/public/v1/ch/post_code.xml"),
    Path("data/public/v1/de/post_code.csv"),
    Path("data/public/v1/de/post_code.json"),
    Path("data/public/v1/de/post_code.xml"),
    Path("data/sources/geofabrik-regions.json"),
    Path("docs/adr/0009-extend-v1-to-dach-post-code-data.md"),
    Path("docs/contracts/CURRENT.md"),
    Path("docs/plans/PLANS.md"),
    Path("docs/plans/PLANS-001-initialize-repository-foundation.md"),
    Path("docs/plans/PLANS-002-germany-post-code-extraction.md"),
    Path("docs/plans/PLANS-003-dach-post-code-expansion.md"),
    Path("pyproject.toml"),
    Path("site/404.html"),
    Path("site/index.html"),
    Path("src/open_postal_codes/countries.py"),
    Path("src/open_postal_codes/osm_extract.py"),
    Path("src/open_postal_codes/post_code.py"),
    Path("src/open_postal_codes/refresh_data.py"),
    Path("tools/repo_checks/language_policy_check.py"),
)

FORBIDDEN_FILES = (
    Path("azure-pipelines.yml"),
    Path(".github/workflows/create-osm-update.yaml"),
    Path("data/public/v1/de/osm/streets.csv"),
    Path("data/public/v1/de/osm/streets.ignore.csv"),
    Path("data/public/v1/de/osm/streets.raw.csv"),
    Path("data/public/v1/li/communes.csv"),
    Path("src/open_postal_codes/csv_filter.py"),
)

REQUIRED_GITIGNORE_SNIPPETS = (
    "out/",
    "htmlcov/",
    ".coverage",
    "*.osm.pbf",
    "*.osm.pbf.part",
    "AGENTS.md",
    "AGENTS.override.md",
)


def main() -> int:
    errors: list[str] = []

    for path in REQUIRED_DIRECTORIES:
        if not path.is_dir():
            errors.append(f"missing directory: {path}")

    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f"missing file: {path}")

    for path in FORBIDDEN_FILES:
        if path.exists():
            errors.append(f"obsolete file still exists: {path}")

    gitignore = Path(".gitignore")
    if gitignore.exists():
        gitignore_text = gitignore.read_text(encoding="utf-8")
        for snippet in REQUIRED_GITIGNORE_SNIPPETS:
            if snippet not in gitignore_text:
                errors.append(f".gitignore missing: {snippet}")

    return fail("project-structure-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
