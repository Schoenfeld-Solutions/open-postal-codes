"""Country configuration for D-A-CH post code extraction and publication."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class GeofabrikRegion:
    """One Geofabrik source file used by the data refresh."""

    name: str
    url: str
    country: str = "de"

    @property
    def md5_url(self) -> str:
        return f"{self.url}.md5"

    @property
    def output_name(self) -> str:
        return f"{self.name}.csv"

    @property
    def metadata_key(self) -> str:
        country = self.country.strip().lower()
        if country == "de":
            return self.name
        return f"{country}/{self.name}"


@dataclass(frozen=True)
class CountryConfig:
    """Static rules for one published country."""

    slug: str
    code: str
    name: str
    adjective: str
    time_zone: str
    post_code_pattern: re.Pattern[str]
    post_code_description: str
    region_boundary_admin_levels: tuple[str, ...]
    county_admin_levels: tuple[str, ...]
    county_fallback_admin_levels: tuple[str, ...]
    geofabrik_regions: tuple[GeofabrikRegion, ...]


GEOFABRIK_GERMANY_BASE_URL: Final = "https://download.geofabrik.de/europe/germany"

GERMANY_SOURCE_NAMES: Final = (
    "baden-wuerttemberg",
    "bayern",
    "berlin",
    "brandenburg",
    "bremen",
    "hamburg",
    "hessen",
    "mecklenburg-vorpommern",
    "niedersachsen",
    "nordrhein-westfalen",
    "rheinland-pfalz",
    "saarland",
    "sachsen",
    "sachsen-anhalt",
    "schleswig-holstein",
    "thueringen",
)

COUNTRY_CONFIGS: Final = (
    CountryConfig(
        slug="de",
        code="DE",
        name="Germany",
        adjective="German",
        time_zone="W. Europe Standard Time",
        post_code_pattern=re.compile(r"^[0-9]{5}$"),
        post_code_description="five-digit German post code",
        region_boundary_admin_levels=("4",),
        county_admin_levels=("6",),
        county_fallback_admin_levels=(),
        geofabrik_regions=tuple(
            GeofabrikRegion(
                name=name,
                url=f"{GEOFABRIK_GERMANY_BASE_URL}/{name}-latest.osm.pbf",
                country="de",
            )
            for name in GERMANY_SOURCE_NAMES
        ),
    ),
    CountryConfig(
        slug="at",
        code="AT",
        name="Austria",
        adjective="Austrian",
        time_zone="W. Europe Standard Time",
        post_code_pattern=re.compile(r"^[0-9]{4}$"),
        post_code_description="four-digit Austrian post code",
        region_boundary_admin_levels=("4",),
        county_admin_levels=("6",),
        county_fallback_admin_levels=(),
        geofabrik_regions=(
            GeofabrikRegion(
                name="austria",
                url="https://download.geofabrik.de/europe/austria-latest.osm.pbf",
                country="at",
            ),
        ),
    ),
    CountryConfig(
        slug="ch",
        code="CH",
        name="Switzerland",
        adjective="Swiss",
        time_zone="W. Europe Standard Time",
        post_code_pattern=re.compile(r"^[0-9]{4}$"),
        post_code_description="four-digit Swiss post code",
        region_boundary_admin_levels=("4",),
        county_admin_levels=("6",),
        county_fallback_admin_levels=(),
        geofabrik_regions=(
            GeofabrikRegion(
                name="switzerland",
                url="https://download.geofabrik.de/europe/switzerland-latest.osm.pbf",
                country="ch",
            ),
        ),
    ),
)

COUNTRY_CONFIGS_BY_SLUG: Final = {country.slug: country for country in COUNTRY_CONFIGS}
COUNTRY_CONFIGS_BY_CODE: Final = {country.code: country for country in COUNTRY_CONFIGS}
DEFAULT_COUNTRY_CONFIG: Final = COUNTRY_CONFIGS_BY_SLUG["de"]


def get_country_config(value: str) -> CountryConfig:
    """Return a country configuration by slug or ISO 3166-1 alpha-2 code."""

    normalized = value.strip()
    if not normalized:
        raise ValueError("country must not be empty")

    slug = normalized.lower()
    if slug in COUNTRY_CONFIGS_BY_SLUG:
        return COUNTRY_CONFIGS_BY_SLUG[slug]

    code = normalized.upper()
    if code in COUNTRY_CONFIGS_BY_CODE:
        return COUNTRY_CONFIGS_BY_CODE[code]

    supported = ", ".join(country.code for country in COUNTRY_CONFIGS)
    raise ValueError(f"country must be one of: {supported}")


def default_geofabrik_regions(
    countries: tuple[CountryConfig, ...] | None = None,
) -> tuple[GeofabrikRegion, ...]:
    """Return the configured Geofabrik source files for the selected countries."""

    selected_countries = countries or COUNTRY_CONFIGS
    return tuple(region for country in selected_countries for region in country.geofabrik_regions)
