"""Check that public docs avoid prohibited tool-attribution references."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail

TEXT_FILE_SUFFIXES = {".html", ".md", ".toml", ".yaml", ".yml"}
SKIPPED_PATHS = {
    Path(".gitignore"),
    Path("tools/repo_checks/reference_policy_check.py"),
}
FORBIDDEN_REFERENCES = (
    "ChatGPT",
    "Claude",
    "Codex",
    "copilot",
    "artificial intelligence",
    "large language model",
)


def iter_checked_files() -> list[Path]:
    paths: list[Path] = []
    for path in Path(".").rglob("*"):
        if not path.is_file() or path in SKIPPED_PATHS:
            continue
        ignored_directories = {".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        if any(part in ignored_directories for part in path.parts):
            continue
        if path.suffix in TEXT_FILE_SUFFIXES:
            paths.append(path)
    return sorted(paths)


def main() -> int:
    errors: list[str] = []

    for path in iter_checked_files():
        text = path.read_text(encoding="utf-8").lower()
        for reference in FORBIDDEN_REFERENCES:
            if reference.lower() in text:
                errors.append(f"{path}: contains prohibited reference")

    return fail("reference-policy-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
