"""Post code records and public file serializers."""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

POST_CODE_TITLE = "post_code"
POST_CODE_FIELDS = ("code", "city", "country", "county", "time_zone")
DEFAULT_COUNTRY = "DE"
DEFAULT_TIME_ZONE = "W. Europe Standard Time"
POST_CODE_PATTERN = re.compile(r"^[0-9]{5}$")
CODE_CITY_PATTERN = re.compile(r"^(?P<code>[0-9]{5})\s+(?P<city>.+)$")
TRAILING_NOTE_PATTERN = re.compile(r"\s*\([^)]*\)\s*$")


@dataclass(frozen=True, order=True)
class PostCodeRecord:
    """One public post code record."""

    code: str
    city: str
    country: str = DEFAULT_COUNTRY
    county: str = ""
    time_zone: str = DEFAULT_TIME_ZONE

    def __post_init__(self) -> None:
        normalized_code = normalize_post_code(self.code)
        normalized_city = normalize_text(self.city)
        normalized_country = normalize_text(self.country).upper()
        normalized_county = normalize_text(self.county)
        normalized_time_zone = normalize_text(self.time_zone)

        if not normalized_code:
            raise ValueError("post code must be a five-digit German post code")
        if not normalized_city:
            raise ValueError("city must not be empty")
        if normalized_country != DEFAULT_COUNTRY:
            raise ValueError("country must be DE")
        if normalized_time_zone != DEFAULT_TIME_ZONE:
            raise ValueError(f"time_zone must be {DEFAULT_TIME_ZONE}")

        object.__setattr__(self, "code", normalized_code)
        object.__setattr__(self, "city", normalized_city)
        object.__setattr__(self, "country", normalized_country)
        object.__setattr__(self, "county", normalized_county)
        object.__setattr__(self, "time_zone", normalized_time_zone)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def normalize_text(value: str | None) -> str:
    """Normalize whitespace in a free-text OSM value."""

    if value is None:
        return ""
    return " ".join(value.strip().split())


def normalize_post_code(value: str | None) -> str:
    """Return a valid German post code or an empty string."""

    normalized = normalize_text(value)
    if not POST_CODE_PATTERN.match(normalized):
        return ""
    return normalized


def parse_boundary_city(post_code: str, values: Sequence[str | None]) -> str:
    """Parse a city from boundary labels shaped like ``12345 City``."""

    normalized_code = normalize_post_code(post_code)
    if not normalized_code:
        return ""

    for value in values:
        normalized_value = normalize_text(value)
        match = CODE_CITY_PATTERN.match(normalized_value)
        if not match or match.group("code") != normalized_code:
            continue
        city = TRAILING_NOTE_PATTERN.sub("", match.group("city")).strip()
        return normalize_text(city)
    return ""


def dedupe_records(records: Iterable[PostCodeRecord]) -> tuple[PostCodeRecord, ...]:
    """Return records sorted by the public deterministic order."""

    return tuple(sorted(set(records)))


def read_post_code_csv(path: Path) -> tuple[PostCodeRecord, ...]:
    """Read public post code CSV records."""

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != POST_CODE_FIELDS:
            raise ValueError(f"{path} does not use the post_code CSV header")
        return dedupe_records(PostCodeRecord(**row) for row in reader)


def write_post_code_csv(records: Iterable[PostCodeRecord], path: Path) -> int:
    """Write public post code CSV and return the record count."""

    ordered_records = dedupe_records(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=POST_CODE_FIELDS, lineterminator="\n")
        writer.writeheader()
        for record in ordered_records:
            writer.writerow(record.to_dict())
    return len(ordered_records)


def write_post_code_json(records: Iterable[PostCodeRecord], path: Path) -> int:
    """Write public post code JSON and return the record count."""

    ordered_records = dedupe_records(records)
    payload: dict[str, Any] = {
        "title": POST_CODE_TITLE,
        "records": [record.to_dict() for record in ordered_records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(ordered_records)


def write_post_code_xml(records: Iterable[PostCodeRecord], path: Path) -> int:
    """Write public post code XML and return the record count."""

    ordered_records = dedupe_records(records)
    root = ElementTree.Element(POST_CODE_TITLE)
    for record in ordered_records:
        element = ElementTree.SubElement(root, "record")
        for field_name in POST_CODE_FIELDS:
            child = ElementTree.SubElement(element, field_name)
            child.text = getattr(record, field_name)

    tree = ElementTree.ElementTree(root)
    ElementTree.indent(tree, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True, short_empty_elements=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n")
    return len(ordered_records)


def write_public_post_code_files(records: Iterable[PostCodeRecord], output_root: Path) -> int:
    """Write CSV, JSON, and XML post code outputs into an API data root."""

    ordered_records = dedupe_records(records)
    write_post_code_csv(ordered_records, output_root / "post_code.csv")
    write_post_code_json(ordered_records, output_root / "post_code.json")
    write_post_code_xml(ordered_records, output_root / "post_code.xml")
    return len(ordered_records)
