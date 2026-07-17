"""Check tracked public D-A-CH data quality guardrails."""

from __future__ import annotations

import csv
import json
import re
import subprocess
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from open_postal_codes.countries import COUNTRY_CONFIGS
from open_postal_codes.refresh_quality import COUNTRY_ABSOLUTE_FLOORS
from tools.repo_checks.common import fail

PUBLIC_DATA_ROOT = Path("data/public/v1")
METADATA_PATH = Path("data/sources/geofabrik-regions.json")
POST_CODE_EXTENSIONS = ("csv", "json", "xml")
MINIMUM_RECORDS_BY_COUNTRY = {
    country: floor.record_count for country, floor in COUNTRY_ABSOLUTE_FLOORS.items()
}
MINIMUM_UNIQUE_POST_CODES_BY_COUNTRY = {
    country: floor.unique_post_code_count for country, floor in COUNTRY_ABSOLUTE_FLOORS.items()
}
SENTINEL_ROWS = {
    "de": ("28195", "Bremen", "DE", "W. Europe Standard Time"),
    "at": ("1010", "Wien", "AT", "W. Europe Standard Time"),
    "ch": ("8001", "Zürich", "CH", "W. Europe Standard Time"),
}
MD5_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def load_metadata_regions(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    regions = payload.get("regions", {})
    if not isinstance(regions, dict):
        return {}
    return {
        str(key): cast(dict[str, Any], value)
        for key, value in regions.items()
        if isinstance(value, dict)
    }


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
    minimum_unique_post_codes_by_country: Mapping[str, int] = MINIMUM_UNIQUE_POST_CODES_BY_COUNTRY,
    sentinel_rows: Mapping[str, tuple[str, str, str, str]] = SENTINEL_ROWS,
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
        unique_post_codes = {
            row.get("code", "") for row in rows if row.get("country") == country.code
        }
        minimum_unique_post_codes = minimum_unique_post_codes_by_country[country.slug]
        if len(unique_post_codes) < minimum_unique_post_codes:
            errors.append(
                f"{csv_path.relative_to(repository_root)} has {len(unique_post_codes)} "
                f"unique post codes; expected at least {minimum_unique_post_codes}"
            )
        empty_state_count = sum(1 for row in rows if not row.get("state", "").strip())
        if empty_state_count:
            errors.append(
                f"{csv_path.relative_to(repository_root)} has {empty_state_count} rows "
                "without state"
            )
        actual_states = {row.get("state", "").strip() for row in rows}
        actual_states.discard("")
        expected_states = {state.name for state in country.states}
        missing_states = sorted(expected_states.difference(actual_states))
        if missing_states:
            errors.append(
                f"{csv_path.relative_to(repository_root)} is missing expected states: "
                f"{', '.join(missing_states)}"
            )
        unexpected_states = sorted(actual_states.difference(expected_states))
        if unexpected_states:
            errors.append(
                f"{csv_path.relative_to(repository_root)} has unexpected states: "
                f"{', '.join(unexpected_states)}"
            )
        sentinel_code, sentinel_city, sentinel_country, sentinel_time_zone = sentinel_rows[
            country.slug
        ]
        if not any(
            row.get("code") == sentinel_code
            and row.get("city") == sentinel_city
            and row.get("country") == sentinel_country
            and row.get("time_zone") == sentinel_time_zone
            and bool(row.get("state", "").strip())
            for row in rows
        ):
            errors.append(
                f"{csv_path.relative_to(repository_root)} is missing sentinel row "
                f"{sentinel_code} {sentinel_city} with {sentinel_country}, state, "
                f"and {sentinel_time_zone}"
            )

    expected_metadata = {
        region.metadata_key: region.url
        for country in COUNTRY_CONFIGS
        for region in country.geofabrik_regions
    }
    expected_state_codes = {
        region.metadata_key: region.required_state_codes
        for country in COUNTRY_CONFIGS
        for region in country.geofabrik_regions
    }
    actual_metadata = load_metadata_regions(repository_root / METADATA_PATH)
    missing_metadata_keys = sorted(set(expected_metadata).difference(actual_metadata))
    if missing_metadata_keys:
        errors.append(f"source metadata is missing keys: {', '.join(missing_metadata_keys)}")
    errors.extend(
        validate_metadata_values(
            expected_metadata,
            actual_metadata,
            expected_state_codes=expected_state_codes,
        )
    )

    errors.extend(validate_tracked_pbf_files(tracked_pbf_files(repository_root)))
    return errors


def validate_metadata_values(
    expected_metadata: Mapping[str, str],
    actual_metadata: Mapping[str, Mapping[str, Any]],
    *,
    expected_state_codes: Mapping[str, tuple[str, ...]] | None = None,
) -> list[str]:
    errors: list[str] = []

    for key, expected_url in expected_metadata.items():
        metadata = actual_metadata.get(key)
        if metadata is None:
            continue

        url = metadata.get("url")
        if url != expected_url:
            errors.append(f"source metadata {key} has unexpected url")
        elif not (
            isinstance(url, str)
            and url.startswith("https://download.geofabrik.de/")
            and url.endswith(".osm.pbf")
        ):
            errors.append(f"source metadata {key} has malformed Geofabrik url")

        content_length = metadata.get("content_length")
        if not isinstance(content_length, int) or content_length <= 0:
            errors.append(f"source metadata {key} must have positive content_length")

        md5 = metadata.get("md5")
        if not isinstance(md5, str) or MD5_PATTERN.match(md5) is None:
            errors.append(f"source metadata {key} must have a 32-character md5")

        for remote_field in ("etag", "last_modified"):
            if remote_field in metadata and not str(metadata[remote_field]).strip():
                errors.append(f"source metadata {key} has empty {remote_field}")

        for timestamp_field in ("accepted_at", "verified_at"):
            if timestamp_field not in metadata:
                continue
            timestamp = metadata[timestamp_field]
            if not isinstance(timestamp, str) or not _is_offset_aware_iso_timestamp(timestamp):
                errors.append(
                    f"source metadata {key} must have an offset-aware ISO 8601 {timestamp_field}"
                )

        record_count = metadata.get("record_count")
        if "record_count" in metadata and (
            not isinstance(record_count, int) or isinstance(record_count, bool) or record_count <= 0
        ):
            errors.append(f"source metadata {key} must have positive record_count")

        unique_post_code_count = metadata.get("unique_post_code_count")
        if "unique_post_code_count" in metadata and (
            not isinstance(unique_post_code_count, int)
            or isinstance(unique_post_code_count, bool)
            or unique_post_code_count <= 0
        ):
            errors.append(f"source metadata {key} must have positive unique_post_code_count")
        if (
            isinstance(record_count, int)
            and not isinstance(record_count, bool)
            and isinstance(unique_post_code_count, int)
            and not isinstance(unique_post_code_count, bool)
            and unique_post_code_count > record_count
        ):
            errors.append(
                f"source metadata {key} unique_post_code_count must not exceed record_count"
            )

        if "state_codes" in metadata:
            state_codes = metadata["state_codes"]
            if not (
                isinstance(state_codes, list)
                and state_codes
                and all(isinstance(code, str) and code.strip() for code in state_codes)
                and len(state_codes) == len(set(state_codes))
            ):
                errors.append(f"source metadata {key} must have unique non-empty state_codes")
            elif expected_state_codes is not None:
                expected_codes = set(expected_state_codes.get(key, ()))
                if set(state_codes) != expected_codes:
                    errors.append(f"source metadata {key} has unexpected state_codes")

    return errors


def _is_offset_aware_iso_timestamp(value: str) -> bool:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return timestamp.tzinfo is not None and timestamp.utcoffset() is not None


def main() -> int:
    return fail("public-data-quality-check", validate_public_data())


if __name__ == "__main__":
    raise SystemExit(main())
