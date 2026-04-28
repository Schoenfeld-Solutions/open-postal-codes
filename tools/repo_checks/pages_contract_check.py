"""Check static Pages API sources and packaging contract."""

from __future__ import annotations

import csv
from pathlib import Path

from open_postal_codes.pages import DATA_FILES
from tools.repo_checks.common import fail

EXPECTED_STREET_HEADER = ["Name", "PostalCode", "Locality", "RegionalKey", "Borough", "Suburb"]
EXPECTED_COMMUNE_HEADER = ["Key", "Name", "ElectoralDistrict"]


def read_header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as stream:
        return next(csv.reader(stream))


def main() -> int:
    errors: list[str] = []
    data_root = Path("data/public/v1")

    for _, relative_path, _ in DATA_FILES:
        source_path = data_root / relative_path
        if not source_path.exists():
            errors.append(f"missing API source file: {source_path}")

    for relative_path in (
        "de/osm/streets.csv",
        "de/osm/streets.raw.csv",
        "de/osm/streets.ignore.csv",
    ):
        path = data_root / relative_path
        if path.exists() and read_header(path) != EXPECTED_STREET_HEADER:
            errors.append(f"{path} has an unexpected CSV header")

    commune_path = data_root / "li/communes.csv"
    if commune_path.exists() and read_header(commune_path) != EXPECTED_COMMUNE_HEADER:
        errors.append(f"{commune_path} has an unexpected CSV header")

    if list(data_root.rglob("*.gz")):
        errors.append("gzip downloads must be generated into the Pages artifact, not tracked data")

    return fail("pages-contract-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
