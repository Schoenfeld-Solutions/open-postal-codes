from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

from open_postal_codes.post_code import (
    POST_CODE_FIELDS,
    PostCodeRecord,
    parse_boundary_city,
    write_post_code_csv,
    write_post_code_json,
    write_post_code_xml,
)

pytestmark = pytest.mark.unit


def test_parse_boundary_city_requires_code_prefix_and_strips_trailing_note() -> None:
    assert parse_boundary_city("28357", ("28357 Bremen (Borgfeld)", None)) == "Bremen"
    assert parse_boundary_city("28357", ("Bremen 28357", "Borgfeld")) == ""


def test_post_code_record_normalizes_and_validates_public_fields() -> None:
    record = PostCodeRecord(code=" 28195 ", city=" Bremen ", county=" Bremen ")

    assert record.to_dict() == {
        "code": "28195",
        "city": "Bremen",
        "country": "DE",
        "county": "Bremen",
        "time_zone": "W. Europe Standard Time",
    }

    with pytest.raises(ValueError, match="post code"):
        PostCodeRecord(code="2819", city="Bremen")
    with pytest.raises(ValueError, match="country"):
        PostCodeRecord(code="28195", city="Bremen", country="FR")


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
    assert xml_root.tag == "post_code"
    assert len(xml_root.findall("record")) == len(csv_records)
