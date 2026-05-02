from __future__ import annotations

from pathlib import Path

import pytest

from open_postal_codes.osm_extract import ExtractionError, extract_post_codes_from_osm
from tests.unit.osm_fixture_builder import (
    boundary_fixture,
    closed_way,
    country_boundary_fixture,
    nodes,
    tagged_node,
    write_osm,
)

pytestmark = pytest.mark.unit


def test_boundary_records_are_canonical_and_county_enriched(tmp_path: Path) -> None:
    path = tmp_path / "boundary.osm"
    write_osm(
        path,
        boundary_fixture(
            "\n".join(
                [
                    nodes(30, [(1, 1), (1, 4), (4, 4), (4, 1)]),
                    closed_way(
                        130,
                        30,
                        {
                            "boundary": "postal_code",
                            "type": "boundary",
                            "postal_code_level": "8",
                            "postal_code": "28195",
                            "note": "28195 Bremen (Central)",
                        },
                    ),
                    tagged_node(
                        200,
                        2,
                        2,
                        {"addr:postcode": "28195", "addr:city": "Wrong City"},
                    ),
                ]
            )
        ),
    )

    result = extract_post_codes_from_osm(path)

    assert [record.to_dict() for record in result.records] == [
        {
            "code": "28195",
            "city": "Bremen",
            "country": "DE",
            "state": "Bremen",
            "county": "County A",
            "time_zone": "W. Europe Standard Time",
            "is_primary_location": True,
            "location_rank": 1,
            "postal_code_rank": 1,
            "source": "postal_boundary",
            "evidence_count": 0,
        }
    ]


def test_regional_extract_can_use_state_boundary_when_country_boundary_is_absent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "regional.osm"
    write_osm(
        path,
        "\n".join(
            [
                nodes(1, [(0, 0), (0, 10), (10, 10), (10, 0)]),
                closed_way(
                    100,
                    1,
                    {
                        "boundary": "administrative",
                        "admin_level": "4",
                        "ISO3166-2": "DE-BW",
                        "name": "Baden-Württemberg",
                    },
                ),
                nodes(10, [(0, 0), (0, 5), (10, 5), (10, 0)]),
                closed_way(
                    110,
                    10,
                    {
                        "boundary": "administrative",
                        "admin_level": "6",
                        "de:amtlicher_gemeindeschluessel": "08111",
                        "name": "County A",
                    },
                ),
                nodes(30, [(1, 1), (1, 4), (4, 4), (4, 1)]),
                closed_way(
                    130,
                    30,
                    {
                        "boundary": "postal_code",
                        "type": "boundary",
                        "postal_code_level": "8",
                        "postal_code": "70173",
                        "note": "70173 Stuttgart",
                    },
                ),
            ]
        ),
    )

    result = extract_post_codes_from_osm(path)

    assert [record.to_dict() for record in result.records] == [
        {
            "code": "70173",
            "city": "Stuttgart",
            "country": "DE",
            "state": "Baden-Württemberg",
            "county": "County A",
            "time_zone": "W. Europe Standard Time",
            "is_primary_location": True,
            "location_rank": 1,
            "postal_code_rank": 1,
            "source": "postal_boundary",
            "evidence_count": 0,
        }
    ]


def test_austrian_boundary_records_use_country_config(tmp_path: Path) -> None:
    path = tmp_path / "austria.osm"
    write_osm(
        path,
        country_boundary_fixture(
            country="AT",
            county_admin_level="6",
            county_name="Wien",
            state_name="Wien",
            state_iso_code="AT-9",
            extra="\n".join(
                [
                    nodes(30, [(1, 1), (1, 4), (4, 4), (4, 1)]),
                    closed_way(
                        130,
                        30,
                        {
                            "boundary": "postal_code",
                            "postal_code_level": "8",
                            "postal_code": "1010",
                            "note": "1010 Wien",
                        },
                    ),
                ]
            ),
        ),
    )

    result = extract_post_codes_from_osm(path, country="AT")

    assert [record.to_dict() for record in result.records] == [
        {
            "code": "1010",
            "city": "Wien",
            "country": "AT",
            "state": "Wien",
            "county": "Wien",
            "time_zone": "W. Europe Standard Time",
            "is_primary_location": True,
            "location_rank": 1,
            "postal_code_rank": 1,
            "source": "postal_boundary",
            "evidence_count": 0,
        }
    ]


def test_swiss_boundary_uses_canton_state_without_county_fallback(tmp_path: Path) -> None:
    path = tmp_path / "switzerland.osm"
    write_osm(
        path,
        country_boundary_fixture(
            country="CH",
            county_admin_level="4",
            county_name="Kanton Zuerich",
            county_iso_code="CH-ZH",
            extra="\n".join(
                [
                    nodes(30, [(1, 1), (1, 4), (4, 4), (4, 1)]),
                    closed_way(
                        130,
                        30,
                        {
                            "boundary": "postal_code",
                            "postal_code_level": "8",
                            "postal_code": "8001",
                            "note": "8001 Zuerich",
                        },
                    ),
                ]
            ),
        ),
    )

    result = extract_post_codes_from_osm(path, country="CH")

    assert [
        (record.code, record.city, record.country, record.state, record.county)
        for record in result.records
    ] == [("8001", "Zuerich", "CH", "Kanton Zuerich", "")]


def test_austrian_address_fallback_rejects_foreign_country_tags(tmp_path: Path) -> None:
    path = tmp_path / "austrian-address.osm"
    write_osm(
        path,
        country_boundary_fixture(
            country="AT",
            county_admin_level="6",
            county_name="Wien",
            state_name="Wien",
            state_iso_code="AT-9",
            extra="\n".join(
                [
                    tagged_node(
                        300,
                        2,
                        2,
                        {"addr:postcode": "1010", "addr:city": "Wien", "addr:country": "AT"},
                    ),
                    tagged_node(
                        301,
                        2.1,
                        2,
                        {"addr:postcode": "1010", "addr:city": "Wien", "addr:country": "AT"},
                    ),
                    tagged_node(
                        302,
                        2.2,
                        2,
                        {"addr:postcode": "1010", "addr:city": "Wien", "addr:country": "AT"},
                    ),
                    tagged_node(
                        400,
                        2,
                        2,
                        {"addr:postcode": "1010", "addr:city": "Foreign", "addr:country": "DE"},
                    ),
                    tagged_node(
                        401,
                        2.1,
                        2,
                        {"addr:postcode": "1010", "addr:city": "Foreign", "addr:country": "DE"},
                    ),
                    tagged_node(
                        402,
                        2.2,
                        2,
                        {"addr:postcode": "1010", "addr:city": "Foreign", "addr:country": "DE"},
                    ),
                ]
            ),
        ),
    )

    result = extract_post_codes_from_osm(path, country="AT")

    assert [
        (record.code, record.city, record.country, record.source) for record in result.records
    ] == [("1010", "Wien", "AT", "address_fallback")]


def test_address_fallback_requires_city_and_never_uses_generic_name(tmp_path: Path) -> None:
    path = tmp_path / "address.osm"
    write_osm(
        path,
        boundary_fixture(
            "\n".join(
                [
                    tagged_node(
                        300,
                        2,
                        2,
                        {"addr:postcode": "33333", "addr:city": "Fallback"},
                    ),
                    tagged_node(
                        301,
                        2.1,
                        2,
                        {"addr:postcode": "33333", "addr:city": "Fallback"},
                    ),
                    tagged_node(
                        302,
                        2.2,
                        2,
                        {"addr:postcode": "33333", "addr:city": "Fallback"},
                    ),
                    tagged_node(303, 2, 2, {"addr:postcode": "22222", "name": "Shop Name"}),
                ]
            ),
        ),
    )

    result = extract_post_codes_from_osm(path)

    assert [record.to_dict() for record in result.records] == [
        {
            "code": "33333",
            "city": "Fallback",
            "country": "DE",
            "state": "Bremen",
            "county": "County A",
            "time_zone": "W. Europe Standard Time",
            "is_primary_location": True,
            "location_rank": 1,
            "postal_code_rank": 1,
            "source": "address_fallback",
            "evidence_count": 3,
        }
    ]


def test_foreign_records_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "foreign.osm"
    write_osm(
        path,
        boundary_fixture(
            "\n".join(
                [
                    nodes(40, [(1, 9.8), (1, 11), (4, 11), (4, 9.8)]),
                    closed_way(
                        140,
                        40,
                        {
                            "boundary": "postal_code",
                            "type": "boundary",
                            "postal_code_level": "8",
                            "postal_code": "57200",
                            "note": "57200 Sarreguemines",
                        },
                    ),
                    nodes(50, [(5, 1), (5, 2), (6, 2), (6, 1)]),
                    closed_way(
                        150,
                        50,
                        {
                            "boundary": "postal_code",
                            "type": "boundary",
                            "postal_code_level": "8",
                            "postal_code": "99999",
                            "country": "FR",
                            "note": "99999 Foreign Tagged",
                        },
                    ),
                    tagged_node(
                        400,
                        2,
                        2,
                        {
                            "addr:postcode": "57200",
                            "addr:city": "Sarreguemines",
                            "addr:country": "FR",
                        },
                    ),
                ]
            )
        ),
    )

    with pytest.raises(ExtractionError, match="zero valid"):
        extract_post_codes_from_osm(path)


def test_postal_boundary_can_emit_multiple_counties(tmp_path: Path) -> None:
    path = tmp_path / "multi-county.osm"
    write_osm(
        path,
        boundary_fixture(
            "\n".join(
                [
                    nodes(50, [(1, 4), (1, 6), (4, 6), (4, 4)]),
                    closed_way(
                        150,
                        50,
                        {
                            "boundary": "postal_code",
                            "type": "boundary",
                            "postal_code_level": "8",
                            "postal_code": "55555",
                            "note": "55555 Split City",
                        },
                    ),
                ]
            )
        ),
    )

    result = extract_post_codes_from_osm(path)

    assert [record.county for record in result.records] == ["County A", "County B"]
    assert [record.is_primary_location for record in result.records] == [True, False]
    assert [record.location_rank for record in result.records] == [1, 2]
    assert [record.postal_code_rank for record in result.records] == [1, 1]


def test_postal_boundary_area_does_not_require_type_boundary_tag(tmp_path: Path) -> None:
    path = tmp_path / "postal-area-without-type.osm"
    write_osm(
        path,
        boundary_fixture(
            "\n".join(
                [
                    nodes(60, [(1, 1), (1, 4), (4, 4), (4, 1)]),
                    closed_way(
                        160,
                        60,
                        {
                            "boundary": "postal_code",
                            "postal_code_level": "8",
                            "postal_code": "28195",
                            "note": "28195 Bremen",
                        },
                    ),
                ]
            )
        ),
    )

    result = extract_post_codes_from_osm(path)

    assert [(record.code, record.city, record.source) for record in result.records] == [
        ("28195", "Bremen", "postal_boundary")
    ]


def test_multi_city_boundary_uses_address_evidence_for_primary_choice(tmp_path: Path) -> None:
    path = tmp_path / "primary-evidence.osm"
    write_osm(
        path,
        boundary_fixture(
            "\n".join(
                [
                    nodes(70, [(1, 1), (1, 4), (4, 4), (4, 1)]),
                    closed_way(
                        170,
                        70,
                        {
                            "boundary": "postal_code",
                            "postal_code_level": "8",
                            "postal_code": "71540",
                            "note": "71540 Murrhardt, Fichtenberg",
                        },
                    ),
                    nodes(80, [(6, 1), (6, 4), (9, 4), (9, 1)]),
                    closed_way(
                        180,
                        80,
                        {
                            "boundary": "postal_code",
                            "postal_code_level": "8",
                            "postal_code": "74427",
                            "note": "74427 Fichtenberg",
                        },
                    ),
                    tagged_node(
                        500,
                        2,
                        2,
                        {"addr:postcode": "71540", "addr:city": "Murrhardt"},
                    ),
                    tagged_node(
                        501,
                        2.1,
                        2,
                        {"addr:postcode": "71540", "addr:city": "Murrhardt"},
                    ),
                    tagged_node(
                        502,
                        2.2,
                        2,
                        {"addr:postcode": "71540", "addr:city": "Murrhardt"},
                    ),
                    tagged_node(
                        510,
                        2,
                        2.1,
                        {"addr:postcode": "71540", "addr:city": "Fichtenberg"},
                    ),
                    tagged_node(
                        520,
                        7,
                        2,
                        {"addr:postcode": "74427", "addr:city": "Fichtenberg"},
                    ),
                    tagged_node(
                        521,
                        7.1,
                        2,
                        {"addr:postcode": "74427", "addr:city": "Fichtenberg"},
                    ),
                    tagged_node(
                        522,
                        7.2,
                        2,
                        {"addr:postcode": "74427", "addr:city": "Fichtenberg"},
                    ),
                    tagged_node(
                        523,
                        7.3,
                        2,
                        {"addr:postcode": "74427", "addr:city": "Fichtenberg"},
                    ),
                ]
            )
        ),
    )

    result = extract_post_codes_from_osm(path)

    primary_by_record = {
        (record.code, record.city): record.is_primary_location for record in result.records
    }
    location_rank_by_record = {
        (record.code, record.city): record.location_rank for record in result.records
    }
    postal_code_rank_by_record = {
        (record.code, record.city): record.postal_code_rank for record in result.records
    }
    evidence_by_record = {
        (record.code, record.city): record.evidence_count for record in result.records
    }

    assert primary_by_record[("71540", "Fichtenberg")] is False
    assert primary_by_record[("74427", "Fichtenberg")] is True
    assert primary_by_record[("71540", "Murrhardt")] is True
    assert location_rank_by_record[("71540", "Fichtenberg")] == 2
    assert location_rank_by_record[("71540", "Murrhardt")] == 1
    assert postal_code_rank_by_record[("71540", "Fichtenberg")] == 2
    assert postal_code_rank_by_record[("74427", "Fichtenberg")] == 1
    assert evidence_by_record[("71540", "Fichtenberg")] == 1
    assert evidence_by_record[("74427", "Fichtenberg")] == 4
