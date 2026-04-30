from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ElementTree
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pytest

from open_postal_codes.post_code import (
    ADDRESS_FALLBACK_SOURCE,
    POST_CODE_FIELDS,
    POSTAL_BOUNDARY_SOURCE,
    PostCodeRecord,
    dedupe_records,
    normalize_bool,
    normalize_non_negative_int,
    parse_boundary_cities,
    parse_boundary_city,
    read_post_code_csv,
    write_post_code_csv,
    write_post_code_json,
    write_post_code_xml,
)

pytestmark = pytest.mark.unit


def test_parse_boundary_city_requires_code_prefix_and_strips_trailing_note() -> None:
    assert parse_boundary_city("28357", ("28357 Bremen (Borgfeld)", None)) == "Bremen"
    assert parse_boundary_city("28357", ("Bremen 28357", "Borgfeld")) == ""


def test_parse_boundary_cities_splits_simple_multi_city_labels() -> None:
    assert parse_boundary_cities("71540", ("71540 Murrhardt, Fichtenberg", None)) == (
        "Murrhardt",
        "Fichtenberg",
    )
    assert parse_boundary_cities("1010", ("1010 Wien, Innere Stadt", None), country="AT") == (
        "Wien",
        "Innere Stadt",
    )


def test_post_code_record_normalizes_and_validates_public_fields() -> None:
    record = PostCodeRecord(
        code=" 28195 ",
        city=" Bremen ",
        state=" Bremen ",
        county=" Bremen ",
        is_primary_location="true",
        location_rank="1",
        postal_code_rank="1",
        source=POSTAL_BOUNDARY_SOURCE,
        evidence_count="42",
    )

    assert record.to_dict() == {
        "code": "28195",
        "city": "Bremen",
        "country": "DE",
        "state": "Bremen",
        "county": "Bremen",
        "time_zone": "W. Europe Standard Time",
        "is_primary_location": True,
        "location_rank": 1,
        "postal_code_rank": 1,
        "source": POSTAL_BOUNDARY_SOURCE,
        "evidence_count": 42,
    }
    assert record.to_text_dict()["is_primary_location"] == "true"

    with pytest.raises(ValueError, match="post code"):
        PostCodeRecord(code="2819", city="Bremen")
    with pytest.raises(ValueError, match="country"):
        PostCodeRecord(code="28195", city="Bremen", country="FR")
    with pytest.raises(ValueError, match="source"):
        PostCodeRecord(code="28195", city="Bremen", source="unknown")
    with pytest.raises(ValueError, match="evidence_count"):
        PostCodeRecord(code="28195", city="Bremen", evidence_count="-1")


def test_post_code_record_accepts_country_specific_dach_codes() -> None:
    austrian_record = PostCodeRecord(code="1010", city="Wien", country="AT")
    swiss_record = PostCodeRecord(code="8001", city="Zuerich", country="CH")

    assert austrian_record.to_dict()["country"] == "AT"
    assert swiss_record.to_dict()["country"] == "CH"
    assert austrian_record.to_dict()["time_zone"] == "W. Europe Standard Time"
    assert swiss_record.to_dict()["time_zone"] == "W. Europe Standard Time"

    with pytest.raises(ValueError, match="four-digit Austrian"):
        PostCodeRecord(code="01010", city="Wien", country="AT")
    with pytest.raises(ValueError, match="four-digit Swiss"):
        PostCodeRecord(code="08001", city="Zuerich", country="CH")
    with pytest.raises(ValueError, match="time_zone"):
        PostCodeRecord(
            code="8001",
            city="Zuerich",
            country="CH",
            time_zone="UTC",
        )


def test_dedupe_records_ranks_shared_post_code_and_multi_code_place() -> None:
    records = [
        PostCodeRecord(
            code="71540",
            city="Fichtenberg",
            county="Landkreis Schwaebisch Hall",
            source=POSTAL_BOUNDARY_SOURCE,
            evidence_count=4,
        ),
        PostCodeRecord(
            code="74427",
            city="Fichtenberg",
            county="Landkreis Schwaebisch Hall",
            source=POSTAL_BOUNDARY_SOURCE,
            evidence_count=1149,
        ),
        PostCodeRecord(
            code="71540",
            city="Murrhardt",
            county="Rems-Murr-Kreis",
            source=POSTAL_BOUNDARY_SOURCE,
            evidence_count=4394,
        ),
    ]

    finalized = {
        (record.code, record.city): (
            record.is_primary_location,
            record.location_rank,
            record.postal_code_rank,
        )
        for record in dedupe_records(records)
    }
    assert finalized == {
        ("71540", "Fichtenberg"): (False, 2, 2),
        ("71540", "Murrhardt"): (True, 1, 1),
        ("74427", "Fichtenberg"): (True, 1, 1),
    }


def test_dedupe_records_validates_generic_ranking_invariants() -> None:
    records = dedupe_records(
        [
            PostCodeRecord(
                code="71540",
                city="Fichtenberg",
                county="Landkreis Schwaebisch Hall",
                source=POSTAL_BOUNDARY_SOURCE,
                evidence_count=4,
            ),
            PostCodeRecord(
                code="71540",
                city="Murrhardt",
                county="Rems-Murr-Kreis",
                source=POSTAL_BOUNDARY_SOURCE,
                evidence_count=4394,
            ),
            PostCodeRecord(
                code="74427",
                city="Fichtenberg",
                county="Landkreis Schwaebisch Hall",
                source=POSTAL_BOUNDARY_SOURCE,
                evidence_count=1149,
            ),
            PostCodeRecord(code="01067", city="Dresden", county="Dresden", evidence_count=1741),
            PostCodeRecord(code="01109", city="Dresden", county="Dresden", evidence_count=4654),
            PostCodeRecord(code="01307", city="Dresden", county="Dresden", evidence_count=1295),
        ]
    )

    assert_ranking_invariants(records)


def test_dedupe_records_ranks_many_post_codes_for_city_level_sorting() -> None:
    records = [
        PostCodeRecord(code="01067", city="Dresden", county="Dresden", evidence_count=1741),
        PostCodeRecord(code="01109", city="Dresden", county="Dresden", evidence_count=4654),
        PostCodeRecord(code="01307", city="Dresden", county="Dresden", evidence_count=1295),
    ]

    finalized = {
        record.code: (
            record.is_primary_location,
            record.location_rank,
            record.postal_code_rank,
        )
        for record in dedupe_records(records)
    }

    assert finalized == {
        "01067": (True, 1, 2),
        "01109": (True, 1, 1),
        "01307": (True, 1, 3),
    }
    assert sum(1 for is_primary, _, _ in finalized.values() if is_primary) == 3
    assert sum(postal_code_rank == 1 for _, _, postal_code_rank in finalized.values()) == 1


def test_writers_emit_same_record_set_in_csv_json_and_xml(tmp_path: Path) -> None:
    records = [
        PostCodeRecord(code="66111", city="Saarbruecken"),
        PostCodeRecord(code="28195", city="Bremen"),
    ]

    csv_path = tmp_path / "post_code.csv"
    json_path = tmp_path / "post_code.json"
    xml_path = tmp_path / "post_code.xml"

    assert write_post_code_csv(records, csv_path) == 2
    assert write_post_code_json(records, json_path) == 2
    assert write_post_code_xml(records, xml_path) == 2

    with csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        assert tuple(reader.fieldnames or ()) == POST_CODE_FIELDS
        csv_records = list(reader)

    json_payload = json.loads(json_path.read_text(encoding="utf-8"))
    xml_root = ElementTree.parse(xml_path).getroot()

    assert json_payload["title"] == "post_code"
    assert len(json_payload["records"]) == len(csv_records)
    assert csv_records[0]["is_primary_location"] in {"true", "false"}
    assert csv_records[0]["location_rank"].isdigit()
    assert csv_records[0]["postal_code_rank"].isdigit()
    assert isinstance(json_payload["records"][0]["is_primary_location"], bool)
    assert isinstance(json_payload["records"][0]["location_rank"], int)
    assert isinstance(json_payload["records"][0]["postal_code_rank"], int)
    assert csv_records[0]["source"] == ADDRESS_FALLBACK_SOURCE
    assert xml_root.tag == "post_code"
    assert len(xml_root.findall("record")) == len(csv_records)
    assert all(record.source == ADDRESS_FALLBACK_SOURCE for record in read_post_code_csv(csv_path))


def assert_ranking_invariants(records: Iterable[PostCodeRecord]) -> None:
    rows = tuple(records)
    primary_by_post_code: Counter[tuple[str, str]] = Counter()
    location_ranks: dict[tuple[str, str], list[int]] = {}
    postal_code_ranks: dict[tuple[str, str, str, str], list[int]] = {}

    for record in rows:
        post_code_key = (record.country, record.code)
        place_key = (
            record.country,
            record.state.casefold(),
            record.county.casefold(),
            record.city.casefold(),
        )
        is_primary_location = normalize_bool(record.is_primary_location)
        location_rank = normalize_non_negative_int(record.location_rank, "location_rank")
        postal_code_rank = normalize_non_negative_int(
            record.postal_code_rank,
            "postal_code_rank",
        )

        location_ranks.setdefault(post_code_key, []).append(location_rank)
        postal_code_ranks.setdefault(place_key, []).append(postal_code_rank)
        assert is_primary_location is (location_rank == 1)
        if is_primary_location:
            primary_by_post_code[post_code_key] += 1

    assert set(primary_by_post_code) == set(location_ranks)
    assert set(primary_by_post_code.values()) == {1}
    for ranks in location_ranks.values():
        assert sorted(ranks) == list(range(1, len(ranks) + 1))
    for ranks in postal_code_ranks.values():
        assert sorted(ranks) == list(range(1, len(ranks) + 1))
