"""Post code records and public file serializers."""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

POST_CODE_TITLE = "post_code"
POST_CODE_FIELDS = (
    "code",
    "city",
    "country",
    "county",
    "time_zone",
    "is_primary_location",
    "location_rank",
    "postal_code_rank",
    "source",
    "evidence_count",
)
DEFAULT_COUNTRY = "DE"
DEFAULT_TIME_ZONE = "W. Europe Standard Time"
PostCodeSource = Literal["postal_boundary", "address_fallback"]
POSTAL_BOUNDARY_SOURCE: PostCodeSource = "postal_boundary"
ADDRESS_FALLBACK_SOURCE: PostCodeSource = "address_fallback"
POST_CODE_SOURCES = (POSTAL_BOUNDARY_SOURCE, ADDRESS_FALLBACK_SOURCE)
POST_CODE_PATTERN = re.compile(r"^[0-9]{5}$")
CODE_CITY_PATTERN = re.compile(r"^(?P<code>[0-9]{5})\s+(?P<city>.+)$")
TRAILING_NOTE_PATTERN = re.compile(r"\s*\([^)]*\)\s*$")
CITY_SEPARATOR_PATTERN = re.compile(r"\s*(?:,|;|\s+und\s+)\s*")
SOURCE_PRIORITY = {
    POSTAL_BOUNDARY_SOURCE: 1,
    ADDRESS_FALLBACK_SOURCE: 0,
}


@dataclass(frozen=True, order=True)
class PostCodeRecord:
    """One public post code record."""

    code: str
    city: str
    country: str = DEFAULT_COUNTRY
    county: str = ""
    time_zone: str = DEFAULT_TIME_ZONE
    is_primary_location: bool | str = False
    location_rank: int | str = 0
    postal_code_rank: int | str = 0
    source: PostCodeSource | str = ADDRESS_FALLBACK_SOURCE
    evidence_count: int | str = 0

    def __post_init__(self) -> None:
        normalized_code = normalize_post_code(self.code)
        normalized_city = normalize_text(self.city)
        normalized_country = normalize_text(self.country).upper()
        normalized_county = normalize_text(self.county)
        normalized_time_zone = normalize_text(self.time_zone)
        normalized_is_primary_location = normalize_bool(self.is_primary_location)
        normalized_location_rank = normalize_non_negative_int(self.location_rank, "location_rank")
        normalized_postal_code_rank = normalize_non_negative_int(
            self.postal_code_rank,
            "postal_code_rank",
        )
        normalized_source = normalize_source(self.source)
        normalized_evidence_count = normalize_non_negative_int(
            self.evidence_count,
            "evidence_count",
        )

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
        object.__setattr__(self, "is_primary_location", normalized_is_primary_location)
        object.__setattr__(self, "location_rank", normalized_location_rank)
        object.__setattr__(self, "postal_code_rank", normalized_postal_code_rank)
        object.__setattr__(self, "source", normalized_source)
        object.__setattr__(self, "evidence_count", normalized_evidence_count)

    def to_dict(self) -> dict[str, str | bool | int]:
        return {
            "code": self.code,
            "city": self.city,
            "country": self.country,
            "county": self.county,
            "time_zone": self.time_zone,
            "is_primary_location": self.is_primary_location,
            "location_rank": self.location_rank,
            "postal_code_rank": self.postal_code_rank,
            "source": self.source,
            "evidence_count": self.evidence_count,
        }

    def to_text_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "city": self.city,
            "country": self.country,
            "county": self.county,
            "time_zone": self.time_zone,
            "is_primary_location": format_bool(self.is_primary_location),
            "location_rank": str(self.location_rank),
            "postal_code_rank": str(self.postal_code_rank),
            "source": self.source,
            "evidence_count": str(self.evidence_count),
        }

    def identity_key(self) -> tuple[str, str, str, str, str]:
        return _identity_key(self)

    def place_key(self) -> tuple[str, str, str]:
        return _place_key(self)

    def location_group_key(self) -> tuple[str, str]:
        return _location_group_key(self)

    def with_rankings(
        self,
        *,
        is_primary_location: bool,
        location_rank: int,
        postal_code_rank: int,
    ) -> PostCodeRecord:
        return PostCodeRecord(
            code=self.code,
            city=self.city,
            country=self.country,
            county=self.county,
            time_zone=self.time_zone,
            is_primary_location=is_primary_location,
            location_rank=location_rank,
            postal_code_rank=postal_code_rank,
            source=self.source,
            evidence_count=self.evidence_count,
        )


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


def normalize_bool(value: bool | str) -> bool:
    """Normalize public boolean values from Python or CSV input."""

    if isinstance(value, bool):
        return value
    normalized = normalize_text(value).lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("is_primary_location must be true or false")


def format_bool(value: bool | str) -> str:
    """Format a boolean for text-based public files."""

    return "true" if normalize_bool(value) else "false"


def normalize_source(value: str) -> PostCodeSource:
    """Normalize and validate the public source enum."""

    normalized = normalize_text(value)
    if normalized == POSTAL_BOUNDARY_SOURCE:
        return POSTAL_BOUNDARY_SOURCE
    if normalized == ADDRESS_FALLBACK_SOURCE:
        return ADDRESS_FALLBACK_SOURCE
    raise ValueError(f"source must be one of: {', '.join(POST_CODE_SOURCES)}")


def normalize_non_negative_int(value: int | str, field_name: str) -> int:
    """Normalize a public non-negative integer value."""

    if isinstance(value, int):
        normalized = value
    else:
        try:
            normalized = int(normalize_text(value))
        except ValueError as error:
            raise ValueError(f"{field_name} must be a non-negative integer") from error
    if normalized < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return normalized


def parse_boundary_city(post_code: str, values: Sequence[str | None]) -> str:
    """Parse a city from boundary labels shaped like ``12345 City``."""

    cities = parse_boundary_cities(post_code, values)
    return cities[0] if cities else ""


def parse_boundary_cities(post_code: str, values: Sequence[str | None]) -> tuple[str, ...]:
    """Parse cities from boundary labels shaped like ``12345 City``."""

    normalized_code = normalize_post_code(post_code)
    if not normalized_code:
        return ()

    for value in values:
        normalized_value = normalize_text(value)
        match = CODE_CITY_PATTERN.match(normalized_value)
        if not match or match.group("code") != normalized_code:
            continue
        city = TRAILING_NOTE_PATTERN.sub("", match.group("city")).strip()
        cities = tuple(
            normalized_city
            for part in CITY_SEPARATOR_PATTERN.split(city)
            if (normalized_city := normalize_text(part))
        )
        if cities:
            return cities
    return ()


def dedupe_records(records: Iterable[PostCodeRecord]) -> tuple[PostCodeRecord, ...]:
    """Return deduplicated records with deterministic location and post-code rankings."""

    best_by_identity: dict[tuple[str, str, str, str, str], PostCodeRecord] = {}
    for record in records:
        current = best_by_identity.get(record.identity_key())
        if current is None:
            best_by_identity[record.identity_key()] = record.with_rankings(
                is_primary_location=False,
                location_rank=0,
                postal_code_rank=0,
            )
            continue
        best_by_identity[record.identity_key()] = merge_duplicate_records(current, record)

    location_ranked_records: list[PostCodeRecord] = []
    by_post_code: dict[tuple[str, str], list[PostCodeRecord]] = {}
    for record in best_by_identity.values():
        by_post_code.setdefault(record.location_group_key(), []).append(record)

    for post_code_records in by_post_code.values():
        for rank, record in enumerate(sorted(post_code_records, key=location_rank_sort_key), 1):
            location_ranked_records.append(
                record.with_rankings(
                    is_primary_location=rank == 1,
                    location_rank=rank,
                    postal_code_rank=0,
                )
            )

    postal_code_ranks: dict[tuple[str, str, str, str, str], int] = {}
    by_place: dict[tuple[str, str, str], list[PostCodeRecord]] = {}
    for record in location_ranked_records:
        by_place.setdefault(record.place_key(), []).append(record)

    for place_records in by_place.values():
        for rank, record in enumerate(sorted(place_records, key=postal_code_rank_sort_key), 1):
            postal_code_ranks[record.identity_key()] = rank

    finalized = [
        record.with_rankings(
            is_primary_location=normalize_bool(record.is_primary_location),
            location_rank=normalize_non_negative_int(record.location_rank, "location_rank"),
            postal_code_rank=postal_code_ranks[record.identity_key()],
        )
        for record in location_ranked_records
    ]

    return tuple(sorted(finalized))


def merge_duplicate_records(left: PostCodeRecord, right: PostCodeRecord) -> PostCodeRecord:
    """Merge duplicate identity rows from overlapping regional sources."""

    left_source = normalize_source(left.source)
    right_source = normalize_source(right.source)
    source = max((left_source, right_source), key=lambda value: SOURCE_PRIORITY[value])
    evidence_count = max(
        normalize_non_negative_int(left.evidence_count, "evidence_count"),
        normalize_non_negative_int(right.evidence_count, "evidence_count"),
    )
    return PostCodeRecord(
        code=left.code,
        city=left.city,
        country=left.country,
        county=left.county,
        time_zone=left.time_zone,
        is_primary_location=False,
        location_rank=0,
        postal_code_rank=0,
        source=source,
        evidence_count=evidence_count,
    )


def location_rank_sort_key(record: PostCodeRecord) -> tuple[int, int, str, str]:
    """Sort location rows inside one post code by quality."""

    evidence_count = normalize_non_negative_int(record.evidence_count, "evidence_count")
    source = normalize_source(record.source)
    return (
        -evidence_count,
        -SOURCE_PRIORITY[source],
        record.city.casefold(),
        record.county.casefold(),
    )


def postal_code_rank_sort_key(record: PostCodeRecord) -> tuple[int, int, str]:
    """Sort post code rows inside one place by quality."""

    evidence_count = normalize_non_negative_int(record.evidence_count, "evidence_count")
    source = normalize_source(record.source)
    return (-evidence_count, -SOURCE_PRIORITY[source], record.code)


def _identity_key(record: PostCodeRecord) -> tuple[str, str, str, str, str]:
    return (record.code, record.city, record.country, record.county, record.time_zone)


def _place_key(record: PostCodeRecord) -> tuple[str, str, str]:
    return (record.country, record.county.casefold(), record.city.casefold())


def _location_group_key(record: PostCodeRecord) -> tuple[str, str]:
    return (record.country, record.code)


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
            writer.writerow(record.to_text_dict())
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
            child.text = record.to_text_dict()[field_name]

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
