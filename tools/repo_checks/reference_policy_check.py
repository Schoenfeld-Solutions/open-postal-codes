"""Check that tracked public text avoids prohibited provenance references."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tools.repo_checks.common import fail

TEXT_FILE_SUFFIXES = {".html", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
TEXT_FILE_NAMES = {".gitattributes", ".gitignore"}
SKIPPED_PATHS = {
    Path("tools/repo_checks/reference_policy_check.py"),
}


def join_fragments(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_SUBSTRINGS = (
    join_fragments("Chat", "GPT"),
    join_fragments("Clau", "de"),
    join_fragments("co", "pilot"),
    join_fragments("Cod", "ex"),
    join_fragments("Open", "AI"),
    join_fragments("AI", "-generated"),
    "large language model",
    join_fragments("vibe ", "coded"),
)
FORBIDDEN_TOKEN_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9])(?:"
    rf"{join_fragments('A', 'I')}|"
    rf"{join_fragments('K', 'I')}|"
    rf"{join_fragments('L', 'L', 'M')}"
    rf")(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def tracked_files() -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return ()
    return tuple(Path(line) for line in completed.stdout.splitlines() if line)


def should_check(path: Path) -> bool:
    return (
        path not in SKIPPED_PATHS
        and path.is_file()
        and (path.suffix in TEXT_FILE_SUFFIXES or path.name in TEXT_FILE_NAMES)
    )


def iter_checked_files() -> tuple[Path, ...]:
    return tuple(sorted(path for path in tracked_files() if should_check(path)))


def reference_errors_for_path(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    lowered = text.lower()
    for reference in FORBIDDEN_SUBSTRINGS:
        if reference.lower() in lowered:
            errors.append(f"{path}: contains prohibited reference")
            return errors
    if FORBIDDEN_TOKEN_PATTERN.search(text):
        errors.append(f"{path}: contains prohibited standalone token")
    return errors


def main() -> int:
    errors: list[str] = []

    for path in iter_checked_files():
        errors.extend(reference_errors_for_path(path))

    return fail("reference-policy-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
