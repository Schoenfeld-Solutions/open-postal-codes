"""Validate a Conventional Commit subject."""

from __future__ import annotations

import os
import re
import sys

ALLOWED_TYPES = {
    "feat",
    "fix",
    "refactor",
    "docs",
    "test",
    "chore",
    "ci",
    "build",
    "perf",
    "revert",
}
FORBIDDEN_DESCRIPTIONS = {"cleanup", "misc", "stuff", "tmp", "updates", "wip"}


def read_subject(arguments: list[str]) -> str:
    subject = os.environ.get("OPEN_POSTAL_CODES_COMMIT_SUBJECT") or " ".join(arguments)
    subject = subject.strip()
    if not subject:
        raise ValueError("Provide a subject through the environment or command line.")
    return subject


def validate_subject(subject: str) -> None:
    match = re.match(
        r"^(?P<type>[a-z]+)\((?P<scope>[a-z][a-z0-9-]*)\): (?P<description>.+)$",
        subject,
    )
    if match is None:
        raise ValueError("Expected '<type>(<scope>): <description>'.")

    commit_type = match.group("type")
    description = match.group("description")

    if commit_type not in ALLOWED_TYPES:
        raise ValueError(f"Unsupported type: {commit_type}.")
    if description.endswith("."):
        raise ValueError("Description must not end with a period.")
    if description.lower() in FORBIDDEN_DESCRIPTIONS:
        raise ValueError("Description is too vague.")
    if description[:1].isupper():
        raise ValueError("Description must start lowercase.")


def main(arguments: list[str] | None = None) -> int:
    try:
        validate_subject(read_subject(sys.argv[1:] if arguments is None else arguments))
    except ValueError as error:
        print(f"commit-subject-check failed: {error}", file=sys.stderr)
        return 1
    print("commit-subject-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
