"""Extract country-specific post code records from OpenStreetMap files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import osmium
from shapely import wkt
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from open_postal_codes.countries import DEFAULT_COUNTRY_CONFIG, CountryConfig, get_country_config
from open_postal_codes.post_code import (
    ADDRESS_FALLBACK_SOURCE,
    POSTAL_BOUNDARY_SOURCE,
    PostCodeRecord,
    dedupe_records,
    normalize_post_code,
    normalize_text,
    parse_boundary_cities,
    write_post_code_csv,
)

MIN_BOUNDARY_COUNTY_INTERSECTION_RATIO = 0.001
DEFAULT_MIN_ADDRESS_EVIDENCE = 3


class ExtractionError(RuntimeError):
    """Raised when an OSM extract cannot produce valid post code data."""


@dataclass(frozen=True)
class CountyBoundary:
    """An administrative boundary used for spatial enrichment."""

    name: str
    geometry: BaseGeometry


@dataclass(frozen=True)
class PostalBoundaryCandidate:
    """A post code boundary candidate before final enrichment."""

    code: str
    cities: tuple[str, ...]
    geometry: BaseGeometry


@dataclass
class AddressAggregate:
    """Aggregated address evidence for one post code and city."""

    count: int
    geometry: BaseGeometry | None


@dataclass
class AddressEvidence:
    """Accepted address evidence for one public record identity."""

    count: int
    geometry: BaseGeometry | None


@dataclass(frozen=True)
class ExtractionResult:
    """Summary for one completed OSM extraction."""

    records: tuple[PostCodeRecord, ...]
    postal_boundary_count: int
    address_candidate_count: int
    dropped_candidate_count: int


class _PostCodeExtractionHandler(osmium.SimpleHandler):
    def __init__(self, country_config: CountryConfig) -> None:
        super().__init__()
        self.country_config = country_config
        self.wkt_factory = osmium.geom.WKTFactory()
        self.country_geometries: list[BaseGeometry] = []
        self.region_geometries: list[BaseGeometry] = []
        self.counties: list[CountyBoundary] = []
        self.fallback_counties: list[CountyBoundary] = []
        self.postal_boundaries: list[PostalBoundaryCandidate] = []
        self.addresses: dict[tuple[str, str], AddressAggregate] = {}
        self.address_candidate_count = 0
        self.dropped_candidate_count = 0

    def node(self, node: Any) -> None:
        tags = _tag_map(node.tags)
        if "addr:postcode" not in tags:
            return
        geometry = _point_from_node(node)
        self._collect_address(tags, geometry)

    def way(self, way: Any) -> None:
        tags = _tag_map(way.tags)
        if "addr:postcode" not in tags:
            return
        if hasattr(way, "is_closed") and way.is_closed():
            return
        geometry = _geometry_from_way(self.wkt_factory, way)
        self._collect_address(tags, geometry)

    def area(self, area: Any) -> None:
        tags = _tag_map(area.tags)
        geometry = _geometry_from_area(self.wkt_factory, area)
        if geometry is None:
            return

        if _is_country_boundary(tags, self.country_config):
            self.country_geometries.append(geometry)
            return

        if _is_region_boundary(tags, self.country_config):
            self.region_geometries.append(geometry)

        if _is_county_boundary(tags, self.country_config):
            name = normalize_text(tags.get("name"))
            if name:
                self.counties.append(CountyBoundary(name=name, geometry=geometry))
            return

        if _is_county_fallback_boundary(tags, self.country_config):
            name = normalize_text(tags.get("name"))
            if name:
                self.fallback_counties.append(CountyBoundary(name=name, geometry=geometry))
            return

        if _is_postal_code_boundary(tags):
            self._collect_postal_boundary(tags, geometry)

        if "addr:postcode" in tags:
            self._collect_address(tags, geometry.representative_point())

    def _collect_postal_boundary(self, tags: dict[str, str], geometry: BaseGeometry) -> None:
        if _has_foreign_country_tag(tags, self.country_config):
            self.dropped_candidate_count += 1
            return

        code = normalize_post_code(
            tags.get("postal_code") or tags.get("postcode"),
            country=self.country_config.code,
        )
        cities = parse_boundary_cities(
            code,
            (tags.get("note"), tags.get("name")),
            country=self.country_config.code,
        )
        if not code or not cities:
            self.dropped_candidate_count += 1
            return
        self.postal_boundaries.append(
            PostalBoundaryCandidate(code=code, cities=cities, geometry=geometry)
        )

    def _collect_address(
        self,
        tags: dict[str, str],
        geometry: BaseGeometry | None,
    ) -> None:
        if _has_foreign_country_tag(tags, self.country_config):
            self.dropped_candidate_count += 1
            return

        code = normalize_post_code(tags.get("addr:postcode"), country=self.country_config.code)
        city = normalize_text(tags.get("addr:city"))
        if not code or not city:
            self.dropped_candidate_count += 1
            return

        key = (code, city)
        existing = self.addresses.get(key)
        if existing is None:
            self.addresses[key] = AddressAggregate(count=1, geometry=geometry)
        else:
            existing.count += 1
            if existing.geometry is None and geometry is not None:
                existing.geometry = geometry
        self.address_candidate_count += 1


def extract_post_codes_from_osm(
    input_path: Path,
    *,
    country: str = DEFAULT_COUNTRY_CONFIG.code,
    min_address_evidence: int = DEFAULT_MIN_ADDRESS_EVIDENCE,
) -> ExtractionResult:
    """Extract post code records from a PBF or OSM XML file."""

    country_config = get_country_config(country)
    handler = _PostCodeExtractionHandler(country_config)
    area_filter = osmium.filter.KeyFilter("boundary", "addr:postcode")
    object_filter = osmium.filter.KeyFilter("boundary", "addr:postcode")
    processor = (
        osmium.FileProcessor(str(input_path)).with_areas(area_filter).with_filter(object_filter)
    )

    for entity in processor:
        if isinstance(entity, osmium.osm.Node):
            handler.node(entity)
        elif isinstance(entity, osmium.osm.Way):
            handler.way(entity)
        elif isinstance(entity, osmium.osm.Area):
            handler.area(entity)

    country_source_geometries = (
        handler.country_geometries
        or handler.region_geometries
        or [county.geometry for county in handler.counties]
        or [county.geometry for county in handler.fallback_counties]
    )
    if not country_source_geometries:
        raise ExtractionError(
            f"{country_config.name} administrative boundary was not found in the OSM file"
        )

    country_geometry = unary_union(country_source_geometries)
    counties = _country_counties(
        country_geometry=country_geometry,
        counties=handler.counties,
        fallback_counties=handler.fallback_counties,
    )
    address_evidence = _accepted_address_evidence(
        addresses=handler.addresses,
        country_geometry=country_geometry,
        counties=counties,
        handler=handler,
    )

    boundary_records: list[PostCodeRecord] = []
    boundary_codes: set[str] = set()
    for candidate in handler.postal_boundaries:
        if not _geometry_representative_in_country(candidate.geometry, country_geometry):
            handler.dropped_candidate_count += 1
            continue
        county_names = _county_names_for_boundary(candidate.geometry, counties)
        for city in candidate.cities:
            candidate_counties = _candidate_counties_for_city(
                code=candidate.code,
                city=city,
                county_names=county_names,
                address_evidence=address_evidence,
            )
            for county_name in candidate_counties:
                boundary_records.append(
                    PostCodeRecord(
                        code=candidate.code,
                        city=city,
                        country=country_config.code,
                        time_zone=country_config.time_zone,
                        county=county_name,
                        source=POSTAL_BOUNDARY_SOURCE,
                        evidence_count=_evidence_count(
                            code=candidate.code,
                            city=city,
                            county=county_name,
                            address_evidence=address_evidence,
                        ),
                    )
                )
        boundary_codes.add(candidate.code)

    address_records: list[PostCodeRecord] = []
    for (code, city, county_name), evidence in address_evidence.items():
        if code in boundary_codes or evidence.count < min_address_evidence:
            continue
        address_records.append(
            PostCodeRecord(
                code=code,
                city=city,
                country=country_config.code,
                time_zone=country_config.time_zone,
                county=county_name,
                source=ADDRESS_FALLBACK_SOURCE,
                evidence_count=evidence.count,
            )
        )

    records = dedupe_records([*boundary_records, *address_records])
    if not records:
        raise ExtractionError("OSM extraction produced zero valid post code records")

    return ExtractionResult(
        records=records,
        postal_boundary_count=len(handler.postal_boundaries),
        address_candidate_count=handler.address_candidate_count,
        dropped_candidate_count=handler.dropped_candidate_count,
    )


def extract_region_to_csv(
    input_path: Path,
    output_path: Path,
    *,
    country: str = DEFAULT_COUNTRY_CONFIG.code,
) -> ExtractionResult:
    """Extract one regional OSM file into a normalized regional CSV file."""

    result = extract_post_codes_from_osm(input_path, country=country)
    write_post_code_csv(result.records, output_path)
    return result


def _tag_map(tags: Any) -> dict[str, str]:
    return {tag.k: tag.v for tag in tags}


def _is_country_boundary(tags: dict[str, str], country_config: CountryConfig) -> bool:
    return (
        tags.get("boundary") == "administrative"
        and tags.get("admin_level") == "2"
        and (tags.get("ISO3166-1:alpha2") or tags.get("ISO3166-1")) == country_config.code
    )


def _is_region_boundary(tags: dict[str, str], country_config: CountryConfig) -> bool:
    iso_code = normalize_text(tags.get("ISO3166-2")).upper()
    return (
        tags.get("boundary") == "administrative"
        and tags.get("admin_level") in country_config.region_boundary_admin_levels
        and iso_code.startswith(f"{country_config.code}-")
    )


def _is_county_boundary(tags: dict[str, str], country_config: CountryConfig) -> bool:
    return (
        tags.get("boundary") == "administrative"
        and tags.get("admin_level") in country_config.county_admin_levels
        and bool(normalize_text(tags.get("name")))
    )


def _is_county_fallback_boundary(tags: dict[str, str], country_config: CountryConfig) -> bool:
    return (
        tags.get("boundary") == "administrative"
        and tags.get("admin_level") in country_config.county_fallback_admin_levels
        and bool(normalize_text(tags.get("name")))
    )


def _is_postal_code_boundary(tags: dict[str, str]) -> bool:
    return (
        tags.get("boundary") == "postal_code"
        and tags.get("postal_code_level", "8") == "8"
        and bool(tags.get("postal_code") or tags.get("postcode"))
    )


def _has_foreign_country_tag(tags: dict[str, str], country_config: CountryConfig) -> bool:
    country = normalize_text(
        tags.get("addr:country") or tags.get("is_in:country_code") or tags.get("country")
    ).upper()
    return bool(country and country != country_config.code)


def _point_from_node(node: Any) -> BaseGeometry | None:
    try:
        if not node.location.valid():
            return None
        return Point(float(node.location.lon), float(node.location.lat))
    except (AttributeError, ValueError, RuntimeError):
        return None


def _geometry_from_way(wkt_factory: Any, way: Any) -> BaseGeometry | None:
    try:
        return wkt.loads(wkt_factory.create_linestring(way))
    except (RuntimeError, ValueError):
        return None


def _geometry_from_area(wkt_factory: Any, area: Any) -> BaseGeometry | None:
    try:
        return wkt.loads(wkt_factory.create_multipolygon(area))
    except (RuntimeError, ValueError):
        return None


def _country_counties(
    *,
    country_geometry: BaseGeometry,
    counties: list[CountyBoundary],
    fallback_counties: list[CountyBoundary],
) -> list[CountyBoundary]:
    country_counties = [
        county
        for county in counties
        if _geometry_overlaps_country(geometry=county.geometry, country_geometry=country_geometry)
    ]
    if country_counties:
        return country_counties
    return [
        county
        for county in fallback_counties
        if _geometry_overlaps_country(geometry=county.geometry, country_geometry=country_geometry)
    ]


def _geometry_overlaps_country(
    *,
    geometry: BaseGeometry,
    country_geometry: BaseGeometry,
) -> bool:
    if geometry.is_empty:
        return False
    representative = geometry.representative_point()
    return bool(country_geometry.covers(representative) or country_geometry.intersects(geometry))


def _geometry_representative_in_country(
    geometry: BaseGeometry,
    country_geometry: BaseGeometry,
) -> bool:
    if geometry.is_empty:
        return False
    return bool(country_geometry.covers(geometry.representative_point()))


def _accepted_address_evidence(
    *,
    addresses: dict[tuple[str, str], AddressAggregate],
    country_geometry: BaseGeometry,
    counties: list[CountyBoundary],
    handler: _PostCodeExtractionHandler,
) -> dict[tuple[str, str, str], AddressEvidence]:
    evidence: dict[tuple[str, str, str], AddressEvidence] = {}
    for (code, city), aggregate in addresses.items():
        if aggregate.geometry is not None and not _geometry_representative_in_country(
            aggregate.geometry,
            country_geometry,
        ):
            handler.dropped_candidate_count += 1
            continue

        county_name = ""
        if aggregate.geometry is not None:
            county_name = _county_name_for_point(
                aggregate.geometry.representative_point(),
                counties,
            )

        key = (code, city, county_name)
        existing = evidence.get(key)
        if existing is None:
            evidence[key] = AddressEvidence(count=aggregate.count, geometry=aggregate.geometry)
        else:
            existing.count += aggregate.count
            if existing.geometry is None and aggregate.geometry is not None:
                existing.geometry = aggregate.geometry
    return evidence


def _candidate_counties_for_city(
    *,
    code: str,
    city: str,
    county_names: tuple[str, ...],
    address_evidence: dict[tuple[str, str, str], AddressEvidence],
) -> tuple[str, ...]:
    if not county_names:
        return ("",)

    counties_with_evidence = tuple(
        county_name
        for county_name in county_names
        if _evidence_count(
            code=code,
            city=city,
            county=county_name,
            address_evidence=address_evidence,
        )
        > 0
    )
    if counties_with_evidence:
        return counties_with_evidence

    evidence_counties = _evidence_counties_for_city(
        code=code,
        city=city,
        address_evidence=address_evidence,
    )
    return evidence_counties or county_names


def _evidence_counties_for_city(
    *,
    code: str,
    city: str,
    address_evidence: dict[tuple[str, str, str], AddressEvidence],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            county
            for (evidence_code, evidence_city, county), evidence in address_evidence.items()
            if evidence_code == code and evidence_city == city and county and evidence.count > 0
        )
    )


def _evidence_count(
    *,
    code: str,
    city: str,
    county: str,
    address_evidence: dict[tuple[str, str, str], AddressEvidence],
) -> int:
    if county:
        evidence = address_evidence.get((code, city, county))
        return evidence.count if evidence is not None else 0
    return sum(
        evidence.count
        for (evidence_code, evidence_city, _), evidence in address_evidence.items()
        if evidence_code == code and evidence_city == city
    )


def _county_names_for_boundary(
    geometry: BaseGeometry,
    counties: list[CountyBoundary],
) -> tuple[str, ...]:
    if geometry.is_empty:
        return ()
    if geometry.area <= 0:
        county_name = _county_name_for_point(geometry.representative_point(), counties)
        return (county_name,) if county_name else ()

    names: list[str] = []
    for county in counties:
        if not county.geometry.intersects(geometry):
            continue
        intersection = county.geometry.intersection(geometry)
        ratio = intersection.area / geometry.area
        if ratio >= MIN_BOUNDARY_COUNTY_INTERSECTION_RATIO:
            names.append(county.name)
    return tuple(sorted(set(names)))


def _county_name_for_point(point: BaseGeometry, counties: list[CountyBoundary]) -> str:
    for county in counties:
        if county.geometry.covers(point):
            return county.name
    return ""


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input OSM PBF or XML file.")
    parser.add_argument("output", type=Path, help="Output normalized post_code CSV file.")
    parser.add_argument(
        "--country",
        default=DEFAULT_COUNTRY_CONFIG.slug,
        help="Country slug or ISO code to extract. Supported values: de, at, ch.",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = parse_arguments(arguments)
    result = extract_region_to_csv(
        parsed_arguments.input,
        parsed_arguments.output,
        country=parsed_arguments.country,
    )
    print(
        "Extracted post codes: "
        f"{len(result.records)} records, "
        f"{result.postal_boundary_count} postal boundaries, "
        f"{result.address_candidate_count} address candidates, "
        f"{result.dropped_candidate_count} dropped candidates."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
