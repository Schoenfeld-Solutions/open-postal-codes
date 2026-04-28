"""Extract German post code records from OpenStreetMap files."""

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

from open_postal_codes.post_code import (
    DEFAULT_COUNTRY,
    PostCodeRecord,
    dedupe_records,
    normalize_post_code,
    normalize_text,
    parse_boundary_city,
    write_post_code_csv,
)

MIN_BOUNDARY_COUNTY_INTERSECTION_RATIO = 0.001
DEFAULT_MIN_ADDRESS_EVIDENCE = 3


class ExtractionError(RuntimeError):
    """Raised when an OSM extract cannot produce valid post code data."""


@dataclass(frozen=True)
class CountyBoundary:
    """A German county boundary used for spatial enrichment."""

    name: str
    geometry: BaseGeometry


@dataclass(frozen=True)
class PostalBoundaryCandidate:
    """A post code boundary candidate before final enrichment."""

    code: str
    city: str
    geometry: BaseGeometry


@dataclass
class AddressAggregate:
    """Aggregated address evidence for one post code and city."""

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
    def __init__(self) -> None:
        super().__init__()
        self.wkt_factory = osmium.geom.WKTFactory()
        self.germany_geometries: list[BaseGeometry] = []
        self.german_state_geometries: list[BaseGeometry] = []
        self.counties: list[CountyBoundary] = []
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

        if _is_germany_boundary(tags):
            self.germany_geometries.append(geometry)
            return

        if _is_german_state_boundary(tags):
            self.german_state_geometries.append(geometry)
            return

        if _is_german_county_boundary(tags):
            name = normalize_text(tags.get("name"))
            if name:
                self.counties.append(CountyBoundary(name=name, geometry=geometry))
            return

        if _is_postal_code_boundary(tags):
            self._collect_postal_boundary(tags, geometry)

        if "addr:postcode" in tags:
            self._collect_address(tags, geometry.representative_point())

    def _collect_postal_boundary(self, tags: dict[str, str], geometry: BaseGeometry) -> None:
        if _has_foreign_country_tag(tags):
            self.dropped_candidate_count += 1
            return

        code = normalize_post_code(tags.get("postal_code") or tags.get("postcode"))
        city = parse_boundary_city(code, (tags.get("note"), tags.get("name")))
        if not code or not city:
            self.dropped_candidate_count += 1
            return
        self.postal_boundaries.append(
            PostalBoundaryCandidate(code=code, city=city, geometry=geometry)
        )

    def _collect_address(
        self,
        tags: dict[str, str],
        geometry: BaseGeometry | None,
    ) -> None:
        if _has_foreign_country_tag(tags):
            self.dropped_candidate_count += 1
            return

        code = normalize_post_code(tags.get("addr:postcode"))
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
    min_address_evidence: int = DEFAULT_MIN_ADDRESS_EVIDENCE,
) -> ExtractionResult:
    """Extract post code records from a PBF or OSM XML file."""

    handler = _PostCodeExtractionHandler()
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

    germany_source_geometries = (
        handler.germany_geometries
        or handler.german_state_geometries
        or [county.geometry for county in handler.counties]
    )
    if not germany_source_geometries:
        raise ExtractionError("German administrative boundary was not found in the OSM file")

    germany_geometry = unary_union(germany_source_geometries)
    counties = [
        county
        for county in handler.counties
        if _geometry_overlaps_germany(county.geometry, germany_geometry)
    ]

    boundary_records: list[PostCodeRecord] = []
    boundary_codes: set[str] = set()
    for candidate in handler.postal_boundaries:
        if not _geometry_representative_in_germany(candidate.geometry, germany_geometry):
            handler.dropped_candidate_count += 1
            continue
        county_names = _county_names_for_boundary(candidate.geometry, counties)
        if county_names:
            for county_name in county_names:
                boundary_records.append(
                    PostCodeRecord(
                        code=candidate.code,
                        city=candidate.city,
                        county=county_name,
                    )
                )
        else:
            boundary_records.append(PostCodeRecord(code=candidate.code, city=candidate.city))
        boundary_codes.add(candidate.code)

    address_records: list[PostCodeRecord] = []
    for (code, city), aggregate in handler.addresses.items():
        if code in boundary_codes or aggregate.count < min_address_evidence:
            continue
        if aggregate.geometry is not None and not _geometry_representative_in_germany(
            aggregate.geometry, germany_geometry
        ):
            handler.dropped_candidate_count += 1
            continue
        county_name = ""
        if aggregate.geometry is not None:
            county_name = _county_name_for_point(
                aggregate.geometry.representative_point(),
                counties,
            )
        address_records.append(PostCodeRecord(code=code, city=city, county=county_name))

    records = dedupe_records([*boundary_records, *address_records])
    if not records:
        raise ExtractionError("OSM extraction produced zero valid post code records")

    return ExtractionResult(
        records=records,
        postal_boundary_count=len(handler.postal_boundaries),
        address_candidate_count=handler.address_candidate_count,
        dropped_candidate_count=handler.dropped_candidate_count,
    )


def extract_region_to_csv(input_path: Path, output_path: Path) -> ExtractionResult:
    """Extract one regional OSM file into a normalized regional CSV file."""

    result = extract_post_codes_from_osm(input_path)
    write_post_code_csv(result.records, output_path)
    return result


def _tag_map(tags: Any) -> dict[str, str]:
    return {tag.k: tag.v for tag in tags}


def _is_germany_boundary(tags: dict[str, str]) -> bool:
    return (
        tags.get("boundary") == "administrative"
        and tags.get("admin_level") == "2"
        and (tags.get("ISO3166-1:alpha2") or tags.get("ISO3166-1")) == DEFAULT_COUNTRY
    )


def _is_german_state_boundary(tags: dict[str, str]) -> bool:
    iso_code = normalize_text(tags.get("ISO3166-2")).upper()
    return (
        tags.get("boundary") == "administrative"
        and tags.get("admin_level") == "4"
        and iso_code.startswith(f"{DEFAULT_COUNTRY}-")
    )


def _is_german_county_boundary(tags: dict[str, str]) -> bool:
    return (
        tags.get("boundary") == "administrative"
        and tags.get("admin_level") == "6"
        and _is_german_admin_key(tags.get("de:amtlicher_gemeindeschluessel"))
    )


def _is_postal_code_boundary(tags: dict[str, str]) -> bool:
    return (
        tags.get("boundary") == "postal_code"
        and tags.get("type") == "boundary"
        and tags.get("postal_code_level", "8") == "8"
        and bool(tags.get("postal_code") or tags.get("postcode"))
    )


def _is_german_admin_key(value: str | None) -> bool:
    normalized = normalize_text(value)
    return normalized.isdigit() and len(normalized) >= 2


def _has_foreign_country_tag(tags: dict[str, str]) -> bool:
    country = normalize_text(
        tags.get("addr:country") or tags.get("is_in:country_code") or tags.get("country")
    ).upper()
    return bool(country and country != DEFAULT_COUNTRY)


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


def _geometry_overlaps_germany(geometry: BaseGeometry, germany_geometry: BaseGeometry) -> bool:
    if geometry.is_empty:
        return False
    representative = geometry.representative_point()
    return bool(germany_geometry.covers(representative) or germany_geometry.intersects(geometry))


def _geometry_representative_in_germany(
    geometry: BaseGeometry,
    germany_geometry: BaseGeometry,
) -> bool:
    if geometry.is_empty:
        return False
    return bool(germany_geometry.covers(geometry.representative_point()))


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
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = parse_arguments(arguments)
    result = extract_region_to_csv(parsed_arguments.input, parsed_arguments.output)
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
