"""Shared helpers for repository checks."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPOSITORY_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def fail(check_name: str, errors: list[str]) -> int:
    if not errors:
        print(f"{check_name} passed.")
        return 0

    print(f"{check_name} failed:")
    for error in errors:
        print(f"- {error}")
    return 1
