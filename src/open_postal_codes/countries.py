"""Country configuration for D-A-CH post code extraction and publication."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Final, Mapping  # noqa: UP035


@dataclass(frozen=True)
class AdministrativeState:
    """One canonical first-level administrative subdivision."""

    code: str
    name: str


@dataclass(frozen=True)
class GeofabrikRegion:
    """One Geofabrik source file used by the data refresh."""

    name: str
    url: str
    country: str = "de"
    primary_state_code: str | None = None
    required_state_codes: tuple[str, ...] = ()

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
class RemoteMetadata:
    """Accepted remote fingerprint and quality evidence for one source."""

    url: str
    content_length: int
    etag: str
    last_modified: str
    md5: str
    accepted_at: str = ""
    verified_at: str = ""
    record_count: int | None = None
    unique_post_code_count: int | None = None
    state_codes: tuple[str, ...] = ()

    def stable_key(self) -> tuple[str, int, str, str, str]:
        """Return the fields identifying one remote candidate."""

        return (self.url, self.content_length, self.etag, self.last_modified, self.md5)


@dataclass(frozen=True)
class DeltaLimits:
    """Maximum accepted changes relative to accepted data."""

    maximum_record_loss_ratio: float
    maximum_unique_post_code_loss_ratio: float
    maximum_growth_ratio: float


@dataclass(frozen=True)
class AbsoluteFloor:
    """Minimum accepted country-level data volume."""

    record_count: int
    unique_post_code_count: int


@dataclass(frozen=True)
class StateRecordCount:
    """Record count for one canonical administrative state."""

    code: str
    name: str
    record_count: int


@dataclass(frozen=True)
class RecordMetrics:
    """Deterministic metrics derived from a candidate record collection."""

    record_count: int
    unique_post_code_count: int
    state_codes: tuple[str, ...]
    state_record_counts: tuple[StateRecordCount, ...]
    empty_state_count: int
    unknown_state_names: tuple[str, ...]
    wrong_country_count: int

    def state_record_count(self, state_code: str) -> int:
        """Return the record count for a state code, or zero when absent."""

        return next(
            (state.record_count for state in self.state_record_counts if state.code == state_code),
            0,
        )


@dataclass(frozen=True)
class QualityDeltas:
    """Signed candidate changes relative to a baseline."""

    record_count_ratio: float | None
    unique_post_code_count_ratio: float | None


@dataclass(frozen=True)
class QualityEvaluation:
    """Quality decision and evidence for one refresh candidate."""

    metrics: RecordMetrics
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    deltas: QualityDeltas | None

    @property
    def is_valid(self) -> bool:
        """Return whether the candidate passed every hard guardrail."""

        return not self.errors


@dataclass(frozen=True)
class CandidateRefreshEvidence:
    """Diagnostics for a candidate that was not promoted."""

    records: int
    unique_post_codes: int
    state_codes: tuple[str, ...]
    observed_state_codes: tuple[str, ...]
    inferred_state_records: int | None
    md5: str
    deltas: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class RegionRefreshResult:
    """Machine-readable outcome for one source."""

    region: str
    status: str
    records: int
    country: str = "de"
    unique_post_codes: int = 0
    state_codes: tuple[str, ...] = ()
    observed_state_codes: tuple[str, ...] = ()
    inferred_state_records: int | None = None
    md5: str = ""
    duration_seconds: float = 0.0
    deltas: dict[str, float | None] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    error_class: str = ""
    error: str = ""
    candidate: CandidateRefreshEvidence | None = None


@dataclass(frozen=True)
class CountryRefreshResult:
    """Machine-readable outcome for one rebuilt country."""

    country: str
    records: int
    unique_post_codes: int = 0
    state_codes: tuple[str, ...] = ()
    deltas: dict[str, float | None] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshResult:
    """Machine-readable outcome for one refresh run."""

    regions: tuple[RegionRefreshResult, ...]
    public_records: int
    countries: tuple[CountryRefreshResult, ...] = ()
    status: str = "success"
    duration_seconds: float = 0.0


def refresh_completion_message(result: RefreshResult) -> str:
    """Build the stable human-readable CLI completion message."""

    counts = {
        status: sum(source.status == status for source in result.regions)
        for status in ("fresh", "unchanged", "reused_last_good")
    }
    return (
        f"Data refresh completed: {counts['fresh']} fresh, "
        f"{counts['unchanged']} unchanged, "
        f"{counts['reused_last_good']} last-known-good sources, "
        f"{len(result.countries)} country outputs, {result.public_records} public records."
    )


def candidate_refresh_evidence(result: RegionRefreshResult) -> CandidateRefreshEvidence:
    """Copy attempted metrics into explicit rejected-candidate evidence."""

    return CandidateRefreshEvidence(
        result.records,
        result.unique_post_codes,
        result.state_codes,
        result.observed_state_codes,
        result.inferred_state_records,
        result.md5,
        result.deltas,
    )


def refresh_report_payload(
    result: RefreshResult,
    *,
    generated_at: str,
    error: str = "",
    error_class: str = "",
) -> dict[str, Any]:
    """Build a secret-free JSON report payload."""

    warnings = [warning for source in result.regions for warning in source.warnings]
    warnings.extend(warning for country in result.countries for warning in country.warnings)
    return {
        "status": result.status,
        "generated_at": generated_at,
        "duration_seconds": result.duration_seconds,
        "sources": [asdict(source) for source in result.regions],
        "countries": [asdict(country) for country in result.countries],
        "warnings": warnings,
        "error_class": error_class,
        "error": error,
    }


def remote_metadata_from_mapping(values: Mapping[str, Any]) -> RemoteMetadata:
    """Decode one backward-compatible source metadata entry."""

    return RemoteMetadata(
        url=str(values["url"]),
        content_length=int(values["content_length"]),
        etag=str(values.get("etag", "")),
        last_modified=str(values.get("last_modified", "")),
        md5=str(values["md5"]),
        accepted_at=str(values.get("accepted_at", "")),
        verified_at=str(values.get("verified_at", "")),
        record_count=values.get("record_count", values.get("records")),
        unique_post_code_count=values.get(
            "unique_post_code_count", values.get("unique_post_codes")
        ),
        state_codes=tuple(values.get("state_codes", ())),
    )


def remote_metadata_to_mapping(metadata: RemoteMetadata) -> dict[str, Any]:
    """Encode one source metadata entry without empty optional fields."""

    values: dict[str, Any] = {
        "url": metadata.url,
        "content_length": metadata.content_length,
    }
    if metadata.etag:
        values["etag"] = metadata.etag
    if metadata.last_modified:
        values["last_modified"] = metadata.last_modified
    values["md5"] = metadata.md5
    optional: dict[str, Any] = {
        "accepted_at": metadata.accepted_at,
        "verified_at": metadata.verified_at,
        "record_count": metadata.record_count,
        "unique_post_code_count": metadata.unique_post_code_count,
        "state_codes": list(metadata.state_codes),
    }
    values.update({key: value for key, value in optional.items() if value not in ("", None, [])})
    return values


class GeofabrikNetworkError(RuntimeError):
    """A Geofabrik request failed."""


class GeofabrikIntegrityError(RuntimeError):
    """A Geofabrik response violated its integrity contract."""


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
    states: tuple[AdministrativeState, ...]
    geofabrik_regions: tuple[GeofabrikRegion, ...]


GEOFABRIK_GERMANY_BASE_URL: Final = "https://download.geofabrik.de/europe/germany"
GEOFABRIK_MD5_PATTERN: Final = re.compile(r"\b(?P<md5>[0-9a-fA-F]{32})\b")
RETRYABLE_HTTP_CODES: Final = frozenset({408, 429, 500, 502, 503, 504})
RETRY_DELAYS_SECONDS: Final = (2.0, 8.0)
MAX_REMOTE_ATTEMPTS: Final = 3
SOURCE_DELTA_LIMITS: Final = DeltaLimits(0.15, 0.12, 0.25)
COUNTRY_DELTA_LIMITS: Final = DeltaLimits(0.10, 0.05, 0.20)
COUNTRY_ABSOLUTE_FLOORS: Final = {
    "de": AbsoluteFloor(8_000, 7_800),
    "at": AbsoluteFloor(2_700, 2_000),
    "ch": AbsoluteFloor(3_500, 3_000),
}
FLOOR_WARNING_MARGIN_RATIO: Final = 0.05

GERMANY_STATES: Final = (
    AdministrativeState("DE-BW", "Baden-Württemberg"),
    AdministrativeState("DE-BY", "Bayern"),
    AdministrativeState("DE-BE", "Berlin"),
    AdministrativeState("DE-BB", "Brandenburg"),
    AdministrativeState("DE-HB", "Bremen"),
    AdministrativeState("DE-HH", "Hamburg"),
    AdministrativeState("DE-HE", "Hessen"),
    AdministrativeState("DE-MV", "Mecklenburg-Vorpommern"),
    AdministrativeState("DE-NI", "Niedersachsen"),
    AdministrativeState("DE-NW", "Nordrhein-Westfalen"),
    AdministrativeState("DE-RP", "Rheinland-Pfalz"),
    AdministrativeState("DE-SL", "Saarland"),
    AdministrativeState("DE-SN", "Sachsen"),
    AdministrativeState("DE-ST", "Sachsen-Anhalt"),
    AdministrativeState("DE-SH", "Schleswig-Holstein"),
    AdministrativeState("DE-TH", "Thüringen"),
)

AUSTRIA_STATES: Final = (
    AdministrativeState("AT-1", "Burgenland"),
    AdministrativeState("AT-2", "Kärnten"),
    AdministrativeState("AT-3", "Niederösterreich"),
    AdministrativeState("AT-4", "Oberösterreich"),
    AdministrativeState("AT-5", "Salzburg"),
    AdministrativeState("AT-6", "Steiermark"),
    AdministrativeState("AT-7", "Tirol"),
    AdministrativeState("AT-8", "Vorarlberg"),
    AdministrativeState("AT-9", "Wien"),
)

SWITZERLAND_STATES: Final = (
    AdministrativeState("CH-AG", "Aargau"),
    AdministrativeState("CH-AR", "Appenzell Ausserrhoden"),
    AdministrativeState("CH-AI", "Appenzell Innerrhoden"),
    AdministrativeState("CH-BL", "Basel-Landschaft"),
    AdministrativeState("CH-BS", "Basel-Stadt"),
    AdministrativeState("CH-BE", "Bern/Berne"),
    AdministrativeState("CH-FR", "Fribourg/Freiburg"),
    AdministrativeState("CH-GE", "Genève"),
    AdministrativeState("CH-GL", "Glarus"),
    AdministrativeState("CH-GR", "Graubünden/Grischun/Grigioni"),
    AdministrativeState("CH-JU", "Jura"),
    AdministrativeState("CH-LU", "Luzern"),
    AdministrativeState("CH-NE", "Neuchâtel"),
    AdministrativeState("CH-NW", "Nidwalden"),
    AdministrativeState("CH-OW", "Obwalden"),
    AdministrativeState("CH-SH", "Schaffhausen"),
    AdministrativeState("CH-SZ", "Schwyz"),
    AdministrativeState("CH-SO", "Solothurn"),
    AdministrativeState("CH-SG", "St. Gallen"),
    AdministrativeState("CH-TG", "Thurgau"),
    AdministrativeState("CH-TI", "Ticino"),
    AdministrativeState("CH-UR", "Uri"),
    AdministrativeState("CH-VS", "Valais/Wallis"),
    AdministrativeState("CH-VD", "Vaud"),
    AdministrativeState("CH-ZG", "Zug"),
    AdministrativeState("CH-ZH", "Zürich"),
)

GERMANY_SOURCE_STATES: Final = (
    ("baden-wuerttemberg", "DE-BW", ("DE-BW",)),
    ("bayern", "DE-BY", ("DE-BY",)),
    ("berlin", "DE-BE", ("DE-BE",)),
    ("brandenburg", "DE-BB", ("DE-BB", "DE-BE")),
    ("bremen", "DE-HB", ("DE-HB",)),
    ("hamburg", "DE-HH", ("DE-HH",)),
    ("hessen", "DE-HE", ("DE-HE",)),
    ("mecklenburg-vorpommern", "DE-MV", ("DE-MV",)),
    ("niedersachsen", "DE-NI", ("DE-NI", "DE-HB")),
    ("nordrhein-westfalen", "DE-NW", ("DE-NW",)),
    ("rheinland-pfalz", "DE-RP", ("DE-RP",)),
    ("saarland", "DE-SL", ("DE-SL",)),
    ("sachsen", "DE-SN", ("DE-SN",)),
    ("sachsen-anhalt", "DE-ST", ("DE-ST",)),
    ("schleswig-holstein", "DE-SH", ("DE-SH",)),
    ("thueringen", "DE-TH", ("DE-TH",)),
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
        states=GERMANY_STATES,
        geofabrik_regions=tuple(
            GeofabrikRegion(
                name=name,
                url=f"{GEOFABRIK_GERMANY_BASE_URL}/{name}-latest.osm.pbf",
                country="de",
                primary_state_code=primary_state_code,
                required_state_codes=required_state_codes,
            )
            for name, primary_state_code, required_state_codes in GERMANY_SOURCE_STATES
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
        states=AUSTRIA_STATES,
        geofabrik_regions=(
            GeofabrikRegion(
                name="austria",
                url="https://download.geofabrik.de/europe/austria-latest.osm.pbf",
                country="at",
                required_state_codes=tuple(state.code for state in AUSTRIA_STATES),
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
        states=SWITZERLAND_STATES,
        geofabrik_regions=(
            GeofabrikRegion(
                name="switzerland",
                url="https://download.geofabrik.de/europe/switzerland-latest.osm.pbf",
                country="ch",
                required_state_codes=tuple(state.code for state in SWITZERLAND_STATES),
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


def default_german_regions() -> tuple[GeofabrikRegion, ...]:
    """Return the configured German regional source contracts."""

    return DEFAULT_COUNTRY_CONFIG.geofabrik_regions


def configured_german_regions(value: str | None) -> tuple[GeofabrikRegion, ...] | None:
    """Resolve a comma-separated subset of configured German source names."""

    if not value:
        return None
    requested = {name.strip() for name in value.split(",") if name.strip()}
    unknown = requested.difference(region.name for region in default_german_regions())
    if unknown:
        raise ValueError(f"unknown Geofabrik region names: {', '.join(sorted(unknown))}")
    return tuple(region for region in default_german_regions() if region.name in requested)


def configured_countries(value: str | None) -> tuple[CountryConfig, ...] | None:
    """Resolve a comma-separated set of configured countries."""

    if not value:
        return None
    return tuple(get_country_config(item) for item in value.split(",") if item.strip())


def configured_selection(country: CountryConfig, regions: tuple[GeofabrikRegion, ...]) -> bool:
    """Return whether selected sources are configured for a country output."""

    selected = {region for region in regions if region.country == country.slug}
    return bool(selected) and selected.issubset(set(country.geofabrik_regions))


def countries_for_regions(regions: tuple[GeofabrikRegion, ...]) -> tuple[CountryConfig, ...]:
    """Return configured countries represented by regional source contracts."""

    selected = {get_country_config(region.country).slug for region in regions}
    return tuple(country for country in COUNTRY_CONFIGS if country.slug in selected)


def source_label(index: int, total: int, region: GeofabrikRegion) -> str:
    """Return a stable progress label for one source."""

    return f"[{index}/{total}] {region.country}/{region.name}"
