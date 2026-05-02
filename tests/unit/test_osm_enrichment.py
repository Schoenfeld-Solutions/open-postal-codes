from __future__ import annotations

from dataclasses import dataclass

import pytest
from shapely.geometry import GeometryCollection, Point, Polygon
from shapely.geometry.base import BaseGeometry

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

pytestmark = pytest.mark.unit


@dataclass
class Aggregate:
    count: int
    geometry: BaseGeometry | None


def test_country_boundaries_keep_overlapping_regions_and_use_fallback_counties() -> None:
    country = Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])
    inside_state = StateBoundary("Inside", Polygon([(1, 1), (1, 2), (2, 2), (2, 1)]))
    outside_state = StateBoundary("Outside", Polygon([(20, 20), (20, 21), (21, 21), (21, 20)]))
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
    states = [StateBoundary("State", country)]
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
    states = [StateBoundary("State", country)]
    counties = [CountyBoundary("County", country)]

    assert geometry_representative_in_country(GeometryCollection(), country) is False
    assert state_names_for_boundary(GeometryCollection(), states) == ()
    assert county_names_for_boundary(GeometryCollection(), counties) == ()
    assert state_names_for_boundary(Point(1, 1), states) == ("State",)
    assert county_names_for_boundary(Point(1, 1), counties) == ("County",)
    assert state_names_for_boundary(Polygon([(1, 1), (1, 2), (2, 2), (2, 1)]), states) == ("State",)


def outside_state_to_county(state: StateBoundary) -> CountyBoundary:
    return CountyBoundary(name=state.name, geometry=state.geometry)
