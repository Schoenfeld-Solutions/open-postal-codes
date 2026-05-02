"""Check module sizes to keep the codebase easy to review."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail

MAX_PRODUCT_LINES = 650
MAX_TEST_LINES = 600
MAX_REPO_CHECK_LINES = 350

PRODUCT_ROOT = Path("src")
TEST_ROOT = Path("tests")
REPO_CHECK_ROOT = Path("tools/repo_checks")


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def iter_python_files(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    return tuple(sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts))


def validate_file_sizes(repository_root: Path = Path(".")) -> list[str]:
    errors: list[str] = []
    limits = (
        (PRODUCT_ROOT, MAX_PRODUCT_LINES, "product module"),
        (TEST_ROOT, MAX_TEST_LINES, "test module"),
        (REPO_CHECK_ROOT, MAX_REPO_CHECK_LINES, "repository check module"),
    )

    for root, limit, label in limits:
        for path in iter_python_files(repository_root / root):
            line_count = count_lines(path)
            if line_count > limit:
                display_path = path.relative_to(repository_root)
                errors.append(f"{label} exceeds {limit} lines: {display_path} ({line_count})")

    return errors


def main() -> int:
    return fail("module-size-check", validate_file_sizes())


if __name__ == "__main__":
    raise SystemExit(main())
