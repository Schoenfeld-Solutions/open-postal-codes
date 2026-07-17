from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from shapely.geometry import GeometryCollection, Point, Polygon
from shapely.geometry.base import BaseGeometry

from open_postal_codes.countries import GeofabrikRegion, get_country_config
from open_postal_codes.osm_enrichment import (
    AddressEvidence,
    CountyBoundary,
    StateBoundary,
    accepted_address_evidence,
    candidate_counties_for_city,
    candidate_states_for_city,
    country_counties,
    country_states,
    county_names_for_boundary,
    evidence_count,
    geometry_representative_in_country,
    state_names_for_boundary,
)
from open_postal_codes.osm_extract import extract_post_codes_from_osm
from tests.unit.osm_fixture_builder import (
    closed_way,
    nodes,
    regional_source_fixture,
    tagged_node,
    write_osm,
)

pytestmark = pytest.mark.unit


@dataclass
class Aggregate:
    count: int
    geometry: BaseGeometry | None


def test_country_boundaries_keep_overlapping_regions_and_use_fallback_counties() -> None:
    country = Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])
    inside_state = StateBoundary(
        "DE-IN",
        "Inside",
        Polygon([(1, 1), (1, 2), (2, 2), (2, 1)]),
    )
    outside_state = StateBoundary(
        "DE-OUT",
        "Outside",
        Polygon([(20, 20), (20, 21), (21, 21), (21, 20)]),
    )
    fallback_county = CountyBoundary("Fallback", Polygon([(3, 3), (3, 4), (4, 4), (4, 3)]))

    assert country_states(country_geometry=country, states=[inside_state, outside_state]) == [
        inside_state
    ]
    assert country_counties(
        country_geometry=country,
        counties=[],
        fallback_counties=[outside_state_to_county(outside_state), fallback_county],
    ) == [fallback_county]


def test_accepted_address_evidence_enriches_and_drops_foreign_geometry() -> None:
    country = Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])
    states = [StateBoundary("AT-9", "State", country)]
    counties = [CountyBoundary("County", country)]

    result = accepted_address_evidence(
        addresses={
            ("1010", "Wien"): Aggregate(count=2, geometry=Point(1, 1)),
            ("1010", "Wien other"): Aggregate(count=1, geometry=Point(2, 2)),
            ("9999", "Foreign"): Aggregate(count=3, geometry=Point(20, 20)),
        },
        country_geometry=country,
        states=states,
        counties=counties,
    )

    assert result.dropped_candidate_count == 1
    assert result.inferred_evidence_keys == frozenset()
    assert result.evidence[("1010", "Wien", "State", "County")].count == 2
    assert result.evidence[("1010", "Wien other", "State", "County")].count == 1


def test_candidate_state_and_county_prefer_matching_address_evidence() -> None:
    address_evidence = {
        ("71540", "Murrhardt", "Baden-Württemberg", "Rems-Murr-Kreis"): AddressEvidence(
            count=4,
            geometry=None,
        )
    }

    assert candidate_states_for_city(
        code="71540",
        city="Murrhardt",
        state_names=("Baden-Württemberg", "Bayern"),
        address_evidence=address_evidence,
    ) == ("Baden-Württemberg",)
    assert candidate_counties_for_city(
        code="71540",
        city="Murrhardt",
        state="Baden-Württemberg",
        county_names=("Rems-Murr-Kreis", "Other"),
        address_evidence=address_evidence,
    ) == ("Rems-Murr-Kreis",)
    assert (
        evidence_count(
            code="71540",
            city="Murrhardt",
            state="Baden-Württemberg",
            county="",
            address_evidence=address_evidence,
        )
        == 4
    )


def test_boundary_names_handle_empty_point_and_area_geometries() -> None:
    country = Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])
    states = [StateBoundary("DE-HB", "State", country)]
    counties = [CountyBoundary("County", country)]

    assert geometry_representative_in_country(GeometryCollection(), country) is False
    assert state_names_for_boundary(GeometryCollection(), states) == ()
    assert county_names_for_boundary(GeometryCollection(), counties) == ()
    assert state_names_for_boundary(Point(1, 1), states) == ("State",)
    assert county_names_for_boundary(Point(1, 1), counties) == ("County",)
    assert state_names_for_boundary(Polygon([(1, 1), (1, 2), (2, 2), (2, 1)]), states) == ("State",)


def test_country_and_source_contracts_cover_all_dach_states() -> None:
    germany = get_country_config("DE")
    austria = get_country_config("AT")
    switzerland = get_country_config("CH")

    assert len(germany.states) == 16
    assert len(austria.states) == 9
    assert len(switzerland.states) == 26
    for country in (germany, austria, switzerland):
        assert len({state.code for state in country.states}) == len(country.states)
        assert len({state.name for state in country.states}) == len(country.states)
        assert all(state.code.startswith(f"{country.code}-") for state in country.states)

    germany_regions = {region.name: region for region in germany.geofabrik_regions}
    assert germany_regions["brandenburg"].primary_state_code == "DE-BB"
    assert germany_regions["brandenburg"].required_state_codes == ("DE-BB", "DE-BE")
    assert germany_regions["niedersachsen"].primary_state_code == "DE-NI"
    assert germany_regions["niedersachsen"].required_state_codes == ("DE-NI", "DE-HB")
    assert all(
        region.primary_state_code in region.required_state_codes
        for region in germany.geofabrik_regions
    )
    assert set(austria.geofabrik_regions[0].required_state_codes) == {
        state.code for state in austria.states
    }
    assert set(switzerland.geofabrik_regions[0].required_state_codes) == {
        state.code for state in switzerland.states
    }


@pytest.mark.parametrize(
    (
        "region_name",
        "embedded_state_code",
        "embedded_state_name",
        "embedded_post_code",
        "embedded_city",
        "primary_post_code",
        "primary_city",
        "primary_state_name",
    ),
    [
        (
            "brandenburg",
            "DE-BE",
            "Berlin",
            "10115",
            "Berlin",
            "14467",
            "Potsdam",
            "Brandenburg",
        ),
        (
            "niedersachsen",
            "DE-HB",
            "Bremen",
            "28195",
            "Bremen",
            "30159",
            "Hannover",
            "Niedersachsen",
        ),
    ],
)
def test_regional_recovery_preserves_embedded_state_and_infers_primary_state(
    tmp_path: Path,
    region_name: str,
    embedded_state_code: str,
    embedded_state_name: str,
    embedded_post_code: str,
    embedded_city: str,
    primary_post_code: str,
    primary_city: str,
    primary_state_name: str,
) -> None:
    path = tmp_path / f"{region_name}.osm"
    write_osm(
        path,
        regional_source_fixture(
            primary_county_name=f"{primary_state_name} County",
            embedded_state_code=embedded_state_code,
            embedded_state_name="Untrusted embedded state label",
            extra="\n".join(
                [
                    nodes(30, [(0.5, 1), (0.5, 2), (1.5, 2), (1.5, 1)]),
                    closed_way(
                        130,
                        30,
                        {
                            "boundary": "postal_code",
                            "postal_code": embedded_post_code,
                            "note": f"{embedded_post_code} {embedded_city}",
                        },
                    ),
                    nodes(40, [(3, 1), (3, 2), (4, 2), (4, 1)]),
                    closed_way(
                        140,
                        40,
                        {
                            "boundary": "postal_code",
                            "postal_code": primary_post_code,
                            "note": f"{primary_post_code} {primary_city}",
                        },
                    ),
                ]
            ),
        ),
    )
    region = next(
        source
        for source in get_country_config("DE").geofabrik_regions
        if source.name == region_name
    )

    result = extract_post_codes_from_osm(path, region=region)

    assert {record.city: record.state for record in result.records} == {
        embedded_city: embedded_state_name,
        primary_city: primary_state_name,
    }
    assert result.observed_state_codes == (embedded_state_code,)
    assert result.inferred_state_records == 1


def test_regional_recovery_infers_address_fallback_state(tmp_path: Path) -> None:
    path = tmp_path / "brandenburg-address.osm"
    write_osm(
        path,
        regional_source_fixture(
            primary_county_name="Potsdam",
            embedded_state_code="DE-BE",
            embedded_state_name="Berlin",
            extra="\n".join(
                [
                    tagged_node(300, 3, 1, {"addr:postcode": "14467", "addr:city": "Potsdam"}),
                    tagged_node(
                        301,
                        3.1,
                        1,
                        {"addr:postcode": "14467", "addr:city": "Potsdam"},
                    ),
                    tagged_node(
                        302,
                        3.2,
                        1,
                        {"addr:postcode": "14467", "addr:city": "Potsdam"},
                    ),
                    tagged_node(
                        310,
                        3,
                        2,
                        {
                            "addr:postcode": "10115",
                            "addr:city": "Fake Berlin",
                            "ISO3166-2": "DE-BE",
                        },
                    ),
                    tagged_node(
                        311,
                        3.1,
                        2,
                        {
                            "addr:postcode": "10115",
                            "addr:city": "Fake Berlin",
                            "ISO3166-2": "DE-BE",
                        },
                    ),
                    tagged_node(
                        312,
                        3.2,
                        2,
                        {
                            "addr:postcode": "10115",
                            "addr:city": "Fake Berlin",
                            "ISO3166-2": "DE-BE",
                        },
                    ),
                ]
            ),
        ),
    )
    region = next(
        source
        for source in get_country_config("DE").geofabrik_regions
        if source.name == "brandenburg"
    )

    result = extract_post_codes_from_osm(path, region=region)

    assert [(record.city, record.state, record.source) for record in result.records] == [
        ("Potsdam", "Brandenburg", "address_fallback")
    ]
    assert result.dropped_candidate_count == 3
    assert result.inferred_state_records == 1


def test_regional_recovery_requires_accepted_embedded_state_geometry(tmp_path: Path) -> None:
    path = tmp_path / "brandenburg-without-berlin.osm"
    write_osm(
        path,
        regional_source_fixture(
            primary_county_name="Potsdam",
            extra="\n".join(
                [
                    nodes(20, [(0, 0), (0, 10), (2, 10), (2, 0)]),
                    closed_way(
                        120,
                        20,
                        {
                            "boundary": "administrative",
                            "admin_level": "4",
                            "ISO3166-2": "DE-BE",
                            "ISO3166-1:alpha2": "DE",
                            "ISO3166-1": "FR",
                            "name": "Berlin",
                        },
                    ),
                    nodes(40, [(3, 1), (3, 2), (4, 2), (4, 1)]),
                    closed_way(
                        140,
                        40,
                        {
                            "boundary": "postal_code",
                            "postal_code": "14467",
                            "note": "14467 Potsdam",
                        },
                    ),
                ]
            ),
        ),
    )
    region = next(
        source
        for source in get_country_config("DE").geofabrik_regions
        if source.name == "brandenburg"
    )

    result = extract_post_codes_from_osm(path, region=region)

    assert [record.state for record in result.records] == [""]
    assert result.observed_state_codes == ("DE-BE",)
    assert result.inferred_state_records == 0


def test_primary_state_is_not_inferred_without_source_contract(tmp_path: Path) -> None:
    path = tmp_path / "regional-without-contract.osm"
    write_osm(
        path,
        regional_source_fixture(
            primary_county_name="Potsdam",
            embedded_state_code="DE-BE",
            embedded_state_name="Berlin",
            extra="\n".join(
                [
                    nodes(40, [(3, 1), (3, 2), (4, 2), (4, 1)]),
                    closed_way(
                        140,
                        40,
                        {
                            "boundary": "postal_code",
                            "postal_code": "14467",
                            "note": "14467 Potsdam",
                        },
                    ),
                ]
            ),
        ),
    )

    result = extract_post_codes_from_osm(path)

    assert [record.state for record in result.records] == [""]
    assert result.inferred_state_records == 0


@pytest.mark.parametrize(
    ("country", "primary_state_code", "post_code"),
    [("at", "AT-9", "1010"), ("ch", "CH-ZH", "8001")],
)
def test_primary_state_inference_is_disabled_outside_germany(
    tmp_path: Path,
    country: str,
    primary_state_code: str,
    post_code: str,
) -> None:
    path = tmp_path / f"{country}-without-state.osm"
    write_osm(
        path,
        regional_source_fixture(
            primary_county_name="County",
            extra="\n".join(
                [
                    nodes(40, [(3, 1), (3, 2), (4, 2), (4, 1)]),
                    closed_way(
                        140,
                        40,
                        {
                            "boundary": "postal_code",
                            "postal_code": post_code,
                            "note": f"{post_code} Place",
                        },
                    ),
                ]
            ),
        ),
    )
    region = GeofabrikRegion(
        country,
        f"https://example.test/{country}.osm.pbf",
        country=country,
        primary_state_code=primary_state_code,
        required_state_codes=(primary_state_code,),
    )

    result = extract_post_codes_from_osm(path, country=country, region=region)

    assert [record.state for record in result.records] == [""]
    assert result.inferred_state_records == 0


def test_unknown_state_geometry_blocks_primary_state_inference(tmp_path: Path) -> None:
    path = tmp_path / "unknown-state.osm"
    write_osm(
        path,
        regional_source_fixture(
            primary_county_name="County",
            extra="\n".join(
                [
                    nodes(20, [(2, 0), (2, 10), (10, 10), (10, 0)]),
                    closed_way(
                        120,
                        20,
                        {
                            "boundary": "administrative",
                            "admin_level": "4",
                            "ISO3166-2": "DE-XX",
                            "name": "Unknown",
                        },
                    ),
                    nodes(40, [(3, 1), (3, 2), (4, 2), (4, 1)]),
                    closed_way(
                        140,
                        40,
                        {
                            "boundary": "postal_code",
                            "postal_code": "39104",
                            "note": "39104 Magdeburg",
                        },
                    ),
                ]
            ),
        ),
    )
    region = next(
        source
        for source in get_country_config("DE").geofabrik_regions
        if source.name == "sachsen-anhalt"
    )

    result = extract_post_codes_from_osm(path, region=region)

    assert [record.state for record in result.records] == [""]
    assert result.observed_state_codes == ("DE-XX",)
    assert result.inferred_state_records == 0


def test_foreign_and_outside_candidates_are_never_inferred(tmp_path: Path) -> None:
    path = tmp_path / "brandenburg-invalid-candidates.osm"
    write_osm(
        path,
        regional_source_fixture(
            primary_county_name="Potsdam",
            embedded_state_code="DE-BE",
            embedded_state_name="Berlin",
            extra="\n".join(
                [
                    nodes(40, [(3, 1), (3, 2), (4, 2), (4, 1)]),
                    closed_way(
                        140,
                        40,
                        {
                            "boundary": "postal_code",
                            "postal_code": "14467",
                            "note": "14467 Potsdam",
                        },
                    ),
                    nodes(50, [(5, 1), (5, 2), (6, 2), (6, 1)]),
                    closed_way(
                        150,
                        50,
                        {
                            "boundary": "postal_code",
                            "postal_code": "99999",
                            "note": "99999 Foreign",
                            "addr:country": "DE",
                            "ISO3166-1": "FR",
                        },
                    ),
                    nodes(60, [(11, 1), (11, 2), (12, 2), (12, 1)]),
                    closed_way(
                        160,
                        60,
                        {
                            "boundary": "postal_code",
                            "postal_code": "14468",
                            "note": "14468 Outside",
                        },
                    ),
                    nodes(70, [(6, 1), (6, 2), (7, 2), (7, 1)]),
                    closed_way(
                        170,
                        70,
                        {
                            "boundary": "postal_code",
                            "postal_code": "39104",
                            "note": "39104 Unknown state",
                            "ISO3166-2": "DE-XX",
                        },
                    ),
                    nodes(80, [(7, 1), (7, 2), (8, 2), (8, 1)]),
                    closed_way(
                        180,
                        80,
                        {
                            "boundary": "postal_code",
                            "postal_code": "28195",
                            "note": "28195 Source foreign",
                            "ISO3166-2": "DE-HB",
                        },
                    ),
                    nodes(90, [(8, 1), (8, 2), (9, 2), (9, 1)]),
                    closed_way(
                        190,
                        90,
                        {
                            "boundary": "postal_code",
                            "postal_code": "10115",
                            "note": "10115 Mismatched embedded state",
                            "ISO3166-2": "DE-BE",
                        },
                    ),
                ]
            ),
        ),
    )
    region = next(
        source
        for source in get_country_config("DE").geofabrik_regions
        if source.name == "brandenburg"
    )

    result = extract_post_codes_from_osm(path, region=region)

    assert [(record.city, record.state) for record in result.records] == [
        ("Potsdam", "Brandenburg")
    ]
    assert result.dropped_candidate_count == 5
    assert result.inferred_state_records == 1


def outside_state_to_county(state: StateBoundary) -> CountyBoundary:
    return CountyBoundary(name=state.name, geometry=state.geometry)
