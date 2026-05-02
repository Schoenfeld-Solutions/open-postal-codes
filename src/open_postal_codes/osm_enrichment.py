"""Pure spatial enrichment helpers for OSM post code extraction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from shapely.geometry.base import BaseGeometry

MIN_BOUNDARY_INTERSECTION_RATIO = 0.001


@dataclass(frozen=True)
class StateBoundary:
    """A first-level administrative boundary used for state enrichment."""

    name: str
    geometry: BaseGeometry


@dataclass(frozen=True)
class CountyBoundary:
    """An administrative boundary used for spatial enrichment."""

    name: str
    geometry: BaseGeometry


@dataclass
class AddressEvidence:
    """Accepted address evidence for one public record identity."""

    count: int
    geometry: BaseGeometry | None


@dataclass(frozen=True)
class AddressEnrichmentResult:
    """Address evidence plus the number of rejected out-of-country candidates."""

    evidence: dict[tuple[str, str, str, str], AddressEvidence]
    dropped_candidate_count: int


class AddressAggregateLike(Protocol):
    """Minimum address aggregate shape needed for enrichment."""

    count: int
    geometry: BaseGeometry | None


def country_counties(
    *,
    country_geometry: BaseGeometry,
    counties: list[CountyBoundary],
    fallback_counties: list[CountyBoundary],
) -> list[CountyBoundary]:
    country_counties = [
        county
        for county in counties
        if geometry_overlaps_country(geometry=county.geometry, country_geometry=country_geometry)
    ]
    if country_counties:
        return country_counties
    return [
        county
        for county in fallback_counties
        if geometry_overlaps_country(geometry=county.geometry, country_geometry=country_geometry)
    ]


def country_states(
    *,
    country_geometry: BaseGeometry,
    states: list[StateBoundary],
) -> list[StateBoundary]:
    return [
        state
        for state in states
        if geometry_overlaps_country(geometry=state.geometry, country_geometry=country_geometry)
    ]


def geometry_overlaps_country(
    *,
    geometry: BaseGeometry,
    country_geometry: BaseGeometry,
) -> bool:
    if geometry.is_empty:
        return False
    representative = geometry.representative_point()
    return bool(country_geometry.covers(representative) or country_geometry.intersects(geometry))


def geometry_representative_in_country(
    geometry: BaseGeometry,
    country_geometry: BaseGeometry,
) -> bool:
    if geometry.is_empty:
        return False
    return bool(country_geometry.covers(geometry.representative_point()))


def accepted_address_evidence(
    *,
    addresses: Mapping[tuple[str, str], AddressAggregateLike],
    country_geometry: BaseGeometry,
    states: list[StateBoundary],
    counties: list[CountyBoundary],
) -> AddressEnrichmentResult:
    evidence: dict[tuple[str, str, str, str], AddressEvidence] = {}
    dropped_candidate_count = 0
    for (code, city), aggregate in addresses.items():
        if aggregate.geometry is not None and not geometry_representative_in_country(
            aggregate.geometry,
            country_geometry,
        ):
            dropped_candidate_count += 1
            continue

        state_name = ""
        county_name = ""
        if aggregate.geometry is not None:
            point = aggregate.geometry.representative_point()
            state_name = state_name_for_point(point, states)
            county_name = county_name_for_point(point, counties)

        key = (code, city, state_name, county_name)
        existing = evidence.get(key)
        if existing is None:
            evidence[key] = AddressEvidence(count=aggregate.count, geometry=aggregate.geometry)
        else:
            existing.count += aggregate.count
            if existing.geometry is None and aggregate.geometry is not None:
                existing.geometry = aggregate.geometry
    return AddressEnrichmentResult(
        evidence=evidence, dropped_candidate_count=dropped_candidate_count
    )


def candidate_counties_for_city(
    *,
    code: str,
    city: str,
    state: str,
    county_names: tuple[str, ...],
    address_evidence: dict[tuple[str, str, str, str], AddressEvidence],
) -> tuple[str, ...]:
    if not county_names:
        return ("",)

    counties_with_evidence = tuple(
        county_name
        for county_name in county_names
        if evidence_count(
            code=code,
            city=city,
            state=state,
            county=county_name,
            address_evidence=address_evidence,
        )
        > 0
    )
    if counties_with_evidence:
        return counties_with_evidence

    evidence_counties = evidence_counties_for_city(
        code=code,
        city=city,
        state=state,
        address_evidence=address_evidence,
    )
    return evidence_counties or county_names


def candidate_states_for_city(
    *,
    code: str,
    city: str,
    state_names: tuple[str, ...],
    address_evidence: dict[tuple[str, str, str, str], AddressEvidence],
) -> tuple[str, ...]:
    if not state_names:
        return ("",)

    states_with_evidence = tuple(
        state_name
        for state_name in state_names
        if evidence_count(
            code=code,
            city=city,
            state=state_name,
            county="",
            address_evidence=address_evidence,
        )
        > 0
    )
    if states_with_evidence:
        return states_with_evidence

    evidence_states = evidence_states_for_city(
        code=code,
        city=city,
        address_evidence=address_evidence,
    )
    return evidence_states or state_names


def evidence_states_for_city(
    *,
    code: str,
    city: str,
    address_evidence: dict[tuple[str, str, str, str], AddressEvidence],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            state
            for (evidence_code, evidence_city, state, _), evidence in address_evidence.items()
            if evidence_code == code and evidence_city == city and state and evidence.count > 0
        )
    )


def evidence_counties_for_city(
    *,
    code: str,
    city: str,
    state: str,
    address_evidence: dict[tuple[str, str, str, str], AddressEvidence],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            county
            for (
                evidence_code,
                evidence_city,
                evidence_state,
                county,
            ), evidence in address_evidence.items()
            if evidence_code == code
            and evidence_city == city
            and evidence_state == state
            and county
            and evidence.count > 0
        )
    )


def evidence_count(
    *,
    code: str,
    city: str,
    state: str,
    county: str,
    address_evidence: dict[tuple[str, str, str, str], AddressEvidence],
) -> int:
    if county:
        evidence = address_evidence.get((code, city, state, county))
        return evidence.count if evidence is not None else 0
    if state:
        total = 0
        for (evidence_code, evidence_city, evidence_state, _), evidence in address_evidence.items():
            if evidence_code == code and evidence_city == city and evidence_state == state:
                total += evidence.count
        return total
    return sum(
        evidence.count
        for (evidence_code, evidence_city, _, _), evidence in address_evidence.items()
        if evidence_code == code and evidence_city == city
    )


def county_names_for_boundary(
    geometry: BaseGeometry,
    counties: list[CountyBoundary],
) -> tuple[str, ...]:
    if geometry.is_empty:
        return ()
    if geometry.area <= 0:
        county_name = county_name_for_point(geometry.representative_point(), counties)
        return (county_name,) if county_name else ()

    names: list[str] = []
    for county in counties:
        if not county.geometry.intersects(geometry):
            continue
        intersection = county.geometry.intersection(geometry)
        ratio = intersection.area / geometry.area
        if ratio >= MIN_BOUNDARY_INTERSECTION_RATIO:
            names.append(county.name)
    return tuple(sorted(set(names)))


def state_names_for_boundary(
    geometry: BaseGeometry,
    states: list[StateBoundary],
) -> tuple[str, ...]:
    if geometry.is_empty:
        return ()
    if geometry.area <= 0:
        state_name = state_name_for_point(geometry.representative_point(), states)
        return (state_name,) if state_name else ()

    names: list[str] = []
    for state in states:
        if not state.geometry.intersects(geometry):
            continue
        intersection = state.geometry.intersection(geometry)
        ratio = intersection.area / geometry.area
        if ratio >= MIN_BOUNDARY_INTERSECTION_RATIO:
            names.append(state.name)
    return tuple(sorted(set(names)))


def state_name_for_point(point: BaseGeometry, states: list[StateBoundary]) -> str:
    for state in states:
        if state.geometry.covers(point):
            return state.name
    return ""


def county_name_for_point(point: BaseGeometry, counties: list[CountyBoundary]) -> str:
    for county in counties:
        if county.geometry.covers(point):
            return county.name
    return ""
