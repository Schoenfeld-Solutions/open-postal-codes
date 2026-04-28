"""Check foundational repository paths."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail

REQUIRED_DIRECTORIES = (
    Path(".github/workflows"),
    Path("data/public/v1/de/osm"),
    Path("data/public/v1/li"),
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
    Path(".github/workflows/pages.yml"),
    Path(".github/workflows/pull-request.yml"),
    Path(".gitignore"),
    Path(".pre-commit-config.yaml"),
    Path("CHANGELOG.md"),
    Path("LICENSE"),
    Path("NOTICE.md"),
    Path("README.md"),
    Path("data/public/v1/de/osm/streets.csv"),
    Path("data/public/v1/de/osm/streets.ignore.csv"),
    Path("data/public/v1/de/osm/streets.raw.csv"),
    Path("data/public/v1/li/communes.csv"),
    Path("docs/contracts/CURRENT.md"),
    Path("docs/plans/PLANS.md"),
    Path("docs/plans/PLANS-001-initialize-repository-foundation.md"),
    Path("pyproject.toml"),
    Path("site/404.html"),
    Path("site/index.html"),
    Path("tools/repo_checks/language_policy_check.py"),
)

FORBIDDEN_FILES = (
    Path("azure-pipelines.yml"),
    Path(".github/workflows/create-osm-update.yaml"),
)

REQUIRED_GITIGNORE_SNIPPETS = (
    "out/",
    "htmlcov/",
    ".coverage",
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
