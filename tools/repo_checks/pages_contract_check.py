"""Check static Pages API sources and packaging contract."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ElementTree
from collections import Counter
from pathlib import Path
from typing import Any, cast

from open_postal_codes.countries import COUNTRY_CONFIGS, CountryConfig
from open_postal_codes.pages import DATA_FILES
from open_postal_codes.post_code import POST_CODE_FIELDS, POST_CODE_SOURCES
from tools.repo_checks.common import fail


def obsolete_primary_field() -> str:
    return "is" + "_primary"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def read_header(path: Path) -> tuple[str, ...]:
    with path.open(newline="", encoding="utf-8") as stream:
        return tuple(next(csv.reader(stream)))


def main() -> int:
    errors: list[str] = []
    data_root = Path("data/public/v1")
    expected_paths = {
        f"{country.slug}/post_code.{extension}"
        for country in COUNTRY_CONFIGS
        for extension in ("csv", "json", "xml")
    }

    data_file_paths = {relative_path for _, relative_path, _, _ in DATA_FILES}
    if data_file_paths != expected_paths:
        errors.append("Pages DATA_FILES does not match the post_code v1 contract")

    for relative_path in expected_paths:
        source_path = data_root / relative_path
        if not source_path.exists():
            errors.append(f"missing API source file: {source_path}")

    for country in COUNTRY_CONFIGS:
        csv_path = data_root / country.slug / "post_code.csv"
        if csv_path.exists():
            header = read_header(csv_path)
            if header != POST_CODE_FIELDS:
                errors.append(f"{csv_path} has an unexpected CSV header")
            if obsolete_primary_field() in header:
                errors.append(f"{csv_path} must not publish the obsolete primary field")
            csv_records = read_rows(csv_path)
            errors.extend(validate_public_records(csv_records, csv_path, country=country))

        json_path = data_root / country.slug / "post_code.json"
        if json_path.exists():
            payload = cast(dict[str, Any], json.loads(json_path.read_text(encoding="utf-8")))
            if payload.get("title") != "post_code" or not isinstance(payload.get("records"), list):
                errors.append(f"{json_path} does not match the post_code JSON contract")
            else:
                json_records = cast(list[dict[str, Any]], payload["records"])
                if any(obsolete_primary_field() in record for record in json_records):
                    errors.append(f"{json_path} must not publish the obsolete primary field")
                if not all(
                    isinstance(record.get("is_primary_location"), bool) for record in json_records
                ):
                    errors.append(f"{json_path} must encode is_primary_location as a JSON boolean")
                if not all(isinstance(record.get("location_rank"), int) for record in json_records):
                    errors.append(f"{json_path} must encode location_rank as a JSON integer")
                if not all(
                    isinstance(record.get("postal_code_rank"), int) for record in json_records
                ):
                    errors.append(f"{json_path} must encode postal_code_rank as a JSON integer")

        xml_path = data_root / country.slug / "post_code.xml"
        if xml_path.exists():
            root = ElementTree.parse(xml_path).getroot()
            if root.tag != "post_code":
                errors.append(f"{xml_path} does not match the post_code XML contract")
            for record in root.findall("record"):
                if [child.tag for child in record] != list(POST_CODE_FIELDS):
                    errors.append(f"{xml_path} has a record with unexpected fields")
                    break

    forbidden_public_files = (
        data_root / "de/osm/streets.csv",
        data_root / "de/osm/streets.raw.csv",
        data_root / "de/osm/streets.ignore.csv",
        data_root / "li/communes.csv",
    )
    for path in forbidden_public_files:
        if path.exists():
            errors.append(f"obsolete API source file still exists: {path}")

    if list(data_root.rglob("*.gz")):
        errors.append("gzip downloads must be generated into the Pages artifact, not tracked data")

    return fail("pages-contract-check", errors)


def validate_public_records(
    records: list[dict[str, str]],
    path: Path,
    *,
    country: CountryConfig | None = None,
) -> list[str]:
    errors: list[str] = []
    primary_counts: Counter[tuple[str, str]] = Counter()
    location_ranks: dict[tuple[str, str], list[int]] = {}
    postal_code_ranks: dict[tuple[str, str, str], list[int]] = {}

    for row_number, record in enumerate(records, start=2):
        if country is not None:
            if record.get("country") != country.code:
                errors.append(f"{path}:{row_number}: country must be {country.code}")
            if not country.post_code_pattern.match(record.get("code", "")):
                errors.append(
                    f"{path}:{row_number}: code must be a {country.post_code_description}"
                )
            if record.get("time_zone") != country.time_zone:
                errors.append(f"{path}:{row_number}: time_zone must be {country.time_zone}")
        if obsolete_primary_field() in record:
            errors.append(f"{path}:{row_number}: obsolete primary field must not be present")
        if record.get("is_primary_location") not in {"true", "false"}:
            errors.append(f"{path}:{row_number}: is_primary_location must be true or false")
        if record.get("source") not in POST_CODE_SOURCES:
            errors.append(f"{path}:{row_number}: source has an unsupported value")
        evidence_count = record.get("evidence_count", "")
        if not evidence_count.isdigit():
            errors.append(f"{path}:{row_number}: evidence_count must be a non-negative integer")
        location_rank = parse_positive_int(record.get("location_rank", ""))
        if location_rank is None:
            errors.append(f"{path}:{row_number}: location_rank must be a positive integer")
            continue
        postal_code_rank = parse_positive_int(record.get("postal_code_rank", ""))
        if postal_code_rank is None:
            errors.append(f"{path}:{row_number}: postal_code_rank must be a positive integer")
            continue

        post_code_key = (record.get("country", ""), record.get("code", ""))
        place_key = (
            record.get("country", ""),
            record.get("county", "").casefold(),
            record.get("city", "").casefold(),
        )
        location_ranks.setdefault(post_code_key, []).append(location_rank)
        postal_code_ranks.setdefault(place_key, []).append(postal_code_rank)

        if (record.get("is_primary_location") == "true") != (location_rank == 1):
            errors.append(
                f"{path}:{row_number}: is_primary_location must be true exactly for location_rank 1"
            )
        if record.get("is_primary_location") == "true":
            primary_counts[post_code_key] += 1

    for post_code_key, count in primary_counts.items():
        if count != 1:
            errors.append(f"{path}: post code {post_code_key} has {count} primary locations")

    missing_primary_post_codes = set(location_ranks).difference(primary_counts.keys())
    if missing_primary_post_codes:
        errors.append(
            f"{path}: {len(missing_primary_post_codes)} post codes do not have a primary location"
        )

    for post_code_key, ranks in location_ranks.items():
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            errors.append(f"{path}: post code {post_code_key} has non-contiguous location ranks")

    for place_key, ranks in postal_code_ranks.items():
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            errors.append(f"{path}: place {place_key} has non-contiguous postal code ranks")

    return errors


def parse_positive_int(value: str) -> int | None:
    if not value.isdigit():
        return None
    parsed = int(value)
    if parsed < 1:
        return None
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
