"""Check license and attribution files."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail


def main() -> int:
    errors: list[str] = []

    license_path = Path("LICENSE")
    notice_path = Path("NOTICE.md")
    readme_path = Path("README.md")

    if not license_path.exists():
        errors.append("missing LICENSE")
    elif "ODC Open Database License (ODbL)" not in license_path.read_text(encoding="utf-8"):
        errors.append("LICENSE must remain the ODbL text")

    for path in (notice_path, readme_path):
        if not path.exists():
            errors.append(f"missing attribution file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for snippet in (
            "ODbL",
            "OpenStreetMap",
            "Geofabrik GmbH",
            "Frank Stueber",
            "Schoenfeld Solutions",
        ):
            if snippet not in text:
                errors.append(f"{path} missing attribution snippet: {snippet}")

    return fail("license-credit-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
