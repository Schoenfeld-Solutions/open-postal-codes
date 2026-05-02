"""Check tracked public D-A-CH data quality guardrails."""

from __future__ import annotations

import csv
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from open_postal_codes.countries import COUNTRY_CONFIGS
from tools.repo_checks.common import fail

PUBLIC_DATA_ROOT = Path("data/public/v1")
METADATA_PATH = Path("data/sources/geofabrik-regions.json")
POST_CODE_EXTENSIONS = ("csv", "json", "xml")
MINIMUM_RECORDS_BY_COUNTRY = {
    "de": 8_000,
    "at": 3_000,
    "ch": 3_500,
}
SENTINEL_ROWS = {
    "de": ("28195", "Bremen"),
    "at": ("1010", "Wien"),
    "ch": ("8001", "Zürich"),
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def load_metadata_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    regions = payload.get("regions", {})
    if not isinstance(regions, dict):
        return set()
    return {str(key) for key in regions}


def tracked_pbf_files(repository_root: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "*.osm.pbf", "*.osm.pbf.part"],
        check=False,
        capture_output=True,
        cwd=repository_root,
        text=True,
    )
    if completed.returncode != 0:
        return ()
    return tuple(line for line in completed.stdout.splitlines() if line)


def validate_tracked_pbf_files(paths: tuple[str, ...]) -> list[str]:
    if not paths:
        return []
    return [f"raw PBF downloads must not be tracked: {', '.join(paths)}"]


def validate_public_data(
    repository_root: Path = Path("."),
    *,
    minimum_records_by_country: Mapping[str, int] = MINIMUM_RECORDS_BY_COUNTRY,
    sentinel_rows: Mapping[str, tuple[str, str]] = SENTINEL_ROWS,
) -> list[str]:
    errors: list[str] = []
    data_root = repository_root / PUBLIC_DATA_ROOT

    for country in COUNTRY_CONFIGS:
        country_root = data_root / country.slug
        for extension in POST_CODE_EXTENSIONS:
            path = country_root / f"post_code.{extension}"
            if not path.exists():
                errors.append(f"missing public data file: {path.relative_to(repository_root)}")

        csv_path = country_root / "post_code.csv"
        if not csv_path.exists():
            continue
        rows = read_rows(csv_path)
        minimum_records = minimum_records_by_country[country.slug]
        if len(rows) < minimum_records:
            errors.append(
                f"{csv_path.relative_to(repository_root)} has {len(rows)} records; "
                f"expected at least {minimum_records}"
            )
        empty_state_count = sum(1 for row in rows if not row.get("state", "").strip())
        if empty_state_count:
            errors.append(
                f"{csv_path.relative_to(repository_root)} has {empty_state_count} rows "
                "without state"
            )
        sentinel_code, sentinel_city = sentinel_rows[country.slug]
        if not any(
            row.get("code") == sentinel_code
            and row.get("city") == sentinel_city
            and row.get("country") == country.code
            for row in rows
        ):
            errors.append(
                f"{csv_path.relative_to(repository_root)} is missing sentinel row "
                f"{sentinel_code} {sentinel_city}"
            )

    required_metadata_keys = {
        region.metadata_key for country in COUNTRY_CONFIGS for region in country.geofabrik_regions
    }
    actual_metadata_keys = load_metadata_keys(repository_root / METADATA_PATH)
    missing_metadata_keys = sorted(required_metadata_keys.difference(actual_metadata_keys))
    if missing_metadata_keys:
        errors.append(f"source metadata is missing keys: {', '.join(missing_metadata_keys)}")

    errors.extend(validate_tracked_pbf_files(tracked_pbf_files(repository_root)))
    return errors


def main() -> int:
    return fail("public-data-quality-check", validate_public_data())


if __name__ == "__main__":
    raise SystemExit(main())
