"""Quality guardrails and diagnostics for refreshed post code candidates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from open_postal_codes.countries import (
    COUNTRY_ABSOLUTE_FLOORS as COUNTRY_ABSOLUTE_FLOORS,
)
from open_postal_codes.countries import (
    COUNTRY_DELTA_LIMITS,
    FLOOR_WARNING_MARGIN_RATIO,
    GEOFABRIK_MD5_PATTERN,
    SOURCE_DELTA_LIMITS,
    CountryConfig,
    DeltaLimits,
    GeofabrikRegion,
    QualityDeltas,
    QualityEvaluation,
    RecordMetrics,
    RemoteMetadata,
    StateRecordCount,
    default_geofabrik_regions,
    refresh_report_payload,
)
from open_postal_codes.countries import (
    CountryRefreshResult as CountryRefreshResult,
)
from open_postal_codes.countries import (
    RefreshResult as RefreshResult,
)
from open_postal_codes.countries import (
    RegionRefreshResult as RegionRefreshResult,
)
from open_postal_codes.post_code import (
    PostCodeRecord,
    dedupe_records,
    iso_timestamp,
    public_country_output_root,
    read_post_code_csv,
    write_json_atomically,
)


@dataclass(frozen=True)
class SourceBaseline:
    """Validated committed records and their last-good eligibility."""

    records: tuple[PostCodeRecord, ...]
    metrics: RecordMetrics
    usable_as_last_good: bool
    provenance_valid: bool = True


@dataclass(frozen=True)
class AcceptedSource:
    """Records and evidence selected for this run."""

    records: tuple[PostCodeRecord, ...]
    metadata: RemoteMetadata
    result: RegionRefreshResult
    promote: bool


LAST_KNOWN_GOOD_MAXIMUM_AGE: Final = timedelta(days=21)


def _provenance_datetime(value: str, field_name: str, *, now: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")
    parsed = parsed.astimezone(UTC)
    if parsed > now.astimezone(UTC):
        raise ValueError(f"{field_name} must not be in the future")
    return parsed


def validated_provenance_timestamp(
    *,
    accepted_at: str = "",
    verified_at: str = "",
    generated_at: str = "",
    now: datetime,
) -> str:
    """Validate every persisted timestamp and return the latest source verification."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a UTC offset")
    values = {"accepted_at": accepted_at, "verified_at": verified_at, "generated_at": generated_at}
    parsed = {
        name: _provenance_datetime(value, name, now=now) for name, value in values.items() if value
    }
    if (
        "accepted_at" in parsed
        and "verified_at" in parsed
        and parsed["accepted_at"] > parsed["verified_at"]
    ):
        raise ValueError("accepted_at must not be after verified_at")
    return verified_at or accepted_at or generated_at


def refresh_generated_at(
    regions: tuple[GeofabrikRegion, ...],
    accepted: Mapping[str, AcceptedSource],
    previous: str,
    *,
    now: datetime,
) -> str:
    """Resolve the global full-refresh timestamp without advancing fallback runs."""

    complete = set(regions) == set(default_geofabrik_regions())
    no_fallback = all(item.result.status in {"fresh", "unchanged"} for item in accepted.values())
    if complete and no_fallback:
        return iso_timestamp(now)
    if not previous:
        raise ValueError("scoped or fallback refresh requires a previous full generated_at")
    try:
        return validated_provenance_timestamp(generated_at=previous, now=now)
    except ValueError as error:
        raise ValueError(f"invalid previous full generated_at: {error}") from error


def build_refresh_result(
    regions: tuple[GeofabrikRegion, ...],
    accepted: Mapping[str, AcceptedSource],
    countries: tuple[CountryRefreshResult, ...],
    status: str,
    duration_seconds: float,
) -> RefreshResult:
    """Build one ordered run result from accepted per-source decisions."""

    source_results = tuple(
        accepted[region.metadata_key].result
        for region in regions
        if region.metadata_key in accepted
    )
    return RefreshResult(
        source_results,
        sum(country.records for country in countries),
        countries,
        status,
        round(duration_seconds, 3),
    )


def source_error_class(error: BaseException) -> str:
    """Classify known source failures without importing infrastructure modules."""

    return {
        "GeofabrikNetworkError": "network",
        "GeofabrikIntegrityError": "integrity",
        "ExtractionError": "extraction",
        "RefreshError": "refresh",
    }.get(type(error).__name__, "quality")


def is_last_known_good_usable(
    accepted_at: str,
    *,
    now: datetime,
    maximum_age: timedelta = LAST_KNOWN_GOOD_MAXIMUM_AGE,
) -> bool:
    """Return whether an ISO-dated last-known-good source is still within its budget."""

    if maximum_age < timedelta(0):
        raise ValueError("maximum_age must not be negative")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a UTC offset")

    accepted = _provenance_datetime(accepted_at, "accepted_at", now=now)
    age = now.astimezone(UTC) - accepted
    return age <= maximum_age


def calculate_record_metrics(
    records: Iterable[PostCodeRecord],
    *,
    country: CountryConfig,
) -> RecordMetrics:
    """Calculate source-independent candidate metrics without performing I/O."""

    state_by_name = {state.name: state for state in country.states}
    state_counts: Counter[str] = Counter()
    post_codes: set[str] = set()
    unknown_state_names: set[str] = set()
    empty_state_count = 0
    wrong_country_count = 0
    record_count = 0

    for record in records:
        record_count += 1
        post_codes.add(record.code)
        if record.country != country.code:
            wrong_country_count += 1

        if not record.state:
            empty_state_count += 1
            continue
        state = state_by_name.get(record.state)
        if state is None:
            unknown_state_names.add(record.state)
            continue
        state_counts[state.code] += 1

    state_record_counts = tuple(
        StateRecordCount(
            code=state.code,
            name=state.name,
            record_count=state_counts[state.code],
        )
        for state in country.states
        if state_counts[state.code]
    )
    return RecordMetrics(
        record_count=record_count,
        unique_post_code_count=len(post_codes),
        state_codes=tuple(state.code for state in state_record_counts),
        state_record_counts=state_record_counts,
        empty_state_count=empty_state_count,
        unknown_state_names=tuple(sorted(unknown_state_names)),
        wrong_country_count=wrong_country_count,
    )


def validate_source_candidate(
    records: Iterable[PostCodeRecord],
    *,
    country: CountryConfig,
    region: GeofabrikRegion,
    baseline: RecordMetrics | None = None,
) -> QualityEvaluation:
    """Validate one regional source candidate against its source contract."""

    metrics = calculate_record_metrics(records, country=country)
    scope = f"source {region.metadata_key}"
    errors, warnings = _validate_common(metrics, country=country, scope=scope)

    if region.country != country.slug:
        errors.append(f"{scope} belongs to {region.country}; expected country {country.slug}")

    known_state_codes = {state.code for state in country.states}
    configured_state_codes = set(region.required_state_codes)
    if region.primary_state_code is not None:
        configured_state_codes.add(region.primary_state_code)
    unknown_configured_codes = sorted(configured_state_codes.difference(known_state_codes))
    if unknown_configured_codes:
        errors.append(
            f"{scope} has unknown configured state codes: {', '.join(unknown_configured_codes)}"
        )

    observed_state_codes = set(metrics.state_codes)
    unexpected_state_codes = sorted(observed_state_codes.difference(configured_state_codes))
    if unexpected_state_codes:
        errors.append(f"{scope} has unexpected states: {', '.join(unexpected_state_codes)}")
    for state_code in sorted(set(region.required_state_codes)):
        if state_code == region.primary_state_code:
            continue
        if state_code not in observed_state_codes:
            errors.append(f"{scope} is missing required state {state_code}")

    if (
        region.primary_state_code is not None
        and metrics.state_record_count(region.primary_state_code) == 0
    ):
        errors.append(f"{scope} has no records for primary state {region.primary_state_code}")

    deltas = _calculate_deltas(metrics, baseline)
    if baseline is not None and deltas is not None:
        _validate_deltas(
            scope=scope,
            candidate=metrics,
            baseline=baseline,
            deltas=deltas,
            limits=SOURCE_DELTA_LIMITS,
            errors=errors,
            warnings=warnings,
        )
    return QualityEvaluation(
        metrics=metrics,
        errors=tuple(errors),
        warnings=tuple(warnings),
        deltas=deltas,
    )


def validate_country_candidate(
    records: Iterable[PostCodeRecord],
    *,
    country: CountryConfig,
    baseline: RecordMetrics | None = None,
) -> QualityEvaluation:
    """Validate a complete country candidate against country-level guardrails."""

    metrics = calculate_record_metrics(records, country=country)
    scope = f"country {country.slug}"
    errors, warnings = _validate_common(metrics, country=country, scope=scope)

    expected_state_codes = {state.code for state in country.states}
    missing_state_codes = sorted(expected_state_codes.difference(metrics.state_codes))
    if missing_state_codes:
        errors.append(f"{scope} is missing expected states: {', '.join(missing_state_codes)}")

    floor = COUNTRY_ABSOLUTE_FLOORS[country.slug]
    _validate_floor(
        scope=scope,
        metric_name="records",
        candidate_value=metrics.record_count,
        floor_value=floor.record_count,
        errors=errors,
        warnings=warnings,
    )
    _validate_floor(
        scope=scope,
        metric_name="unique post codes",
        candidate_value=metrics.unique_post_code_count,
        floor_value=floor.unique_post_code_count,
        errors=errors,
        warnings=warnings,
    )

    deltas = _calculate_deltas(metrics, baseline)
    if baseline is not None and deltas is not None:
        _validate_deltas(
            scope=scope,
            candidate=metrics,
            baseline=baseline,
            deltas=deltas,
            limits=COUNTRY_DELTA_LIMITS,
            errors=errors,
            warnings=warnings,
        )
    return QualityEvaluation(
        metrics=metrics,
        errors=tuple(errors),
        warnings=tuple(warnings),
        deltas=deltas,
    )


def _validate_common(
    metrics: RecordMetrics,
    *,
    country: CountryConfig,
    scope: str,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    if metrics.empty_state_count:
        errors.append(f"{scope} has {metrics.empty_state_count} records without state")
    if metrics.unknown_state_names:
        errors.append(f"{scope} has unknown state names: {', '.join(metrics.unknown_state_names)}")
    if metrics.wrong_country_count:
        errors.append(
            f"{scope} has {metrics.wrong_country_count} records outside country {country.code}"
        )
    return errors, []


def _calculate_deltas(
    candidate: RecordMetrics,
    baseline: RecordMetrics | None,
) -> QualityDeltas | None:
    if baseline is None:
        return None
    return QualityDeltas(
        record_count_ratio=_change_ratio(candidate.record_count, baseline.record_count),
        unique_post_code_count_ratio=_change_ratio(
            candidate.unique_post_code_count,
            baseline.unique_post_code_count,
        ),
    )


def _change_ratio(candidate_value: int, baseline_value: int) -> float | None:
    if baseline_value == 0:
        return None
    return (candidate_value - baseline_value) / baseline_value


def _validate_floor(
    *,
    scope: str,
    metric_name: str,
    candidate_value: int,
    floor_value: int,
    errors: list[str],
    warnings: list[str],
) -> None:
    if candidate_value < floor_value:
        errors.append(f"{scope} has {candidate_value} {metric_name}; minimum is {floor_value}")
    elif candidate_value <= floor_value * (1 + FLOOR_WARNING_MARGIN_RATIO):
        warnings.append(
            f"{scope} has {candidate_value} {metric_name}, within 5% of minimum {floor_value}"
        )


def _validate_deltas(
    *,
    scope: str,
    candidate: RecordMetrics,
    baseline: RecordMetrics,
    deltas: QualityDeltas,
    limits: DeltaLimits,
    errors: list[str],
    warnings: list[str],
) -> None:
    _validate_metric_delta(
        scope=scope,
        metric_name="records",
        candidate_value=candidate.record_count,
        baseline_value=baseline.record_count,
        change_ratio=deltas.record_count_ratio,
        maximum_loss_ratio=limits.maximum_record_loss_ratio,
        maximum_growth_ratio=limits.maximum_growth_ratio,
        errors=errors,
        warnings=warnings,
    )
    _validate_metric_delta(
        scope=scope,
        metric_name="unique post codes",
        candidate_value=candidate.unique_post_code_count,
        baseline_value=baseline.unique_post_code_count,
        change_ratio=deltas.unique_post_code_count_ratio,
        maximum_loss_ratio=limits.maximum_unique_post_code_loss_ratio,
        maximum_growth_ratio=limits.maximum_growth_ratio,
        errors=errors,
        warnings=warnings,
    )


def _validate_metric_delta(
    *,
    scope: str,
    metric_name: str,
    candidate_value: int,
    baseline_value: int,
    change_ratio: float | None,
    maximum_loss_ratio: float,
    maximum_growth_ratio: float,
    errors: list[str],
    warnings: list[str],
) -> None:
    if change_ratio is None:
        return

    loss_ratio = -change_ratio
    if loss_ratio > maximum_loss_ratio + 1e-12:
        errors.append(
            f"{scope} lost {loss_ratio:.1%} of {metric_name} "
            f"({baseline_value} -> {candidate_value}); maximum loss is {maximum_loss_ratio:.1%}"
        )
    elif loss_ratio >= maximum_loss_ratio / 2:
        warnings.append(
            f"{scope} lost {loss_ratio:.1%} of {metric_name} "
            f"({baseline_value} -> {candidate_value})"
        )

    if change_ratio > maximum_growth_ratio + 1e-12:
        errors.append(
            f"{scope} grew {change_ratio:.1%} in {metric_name} "
            f"({baseline_value} -> {candidate_value}); maximum growth is {maximum_growth_ratio:.1%}"
        )
    elif change_ratio >= maximum_growth_ratio / 2:
        warnings.append(
            f"{scope} grew {change_ratio:.1%} in {metric_name} "
            f"({baseline_value} -> {candidate_value})"
        )


def validate_observed_state_codes(
    observed_state_codes: Iterable[str],
    *,
    country: CountryConfig,
    region: GeofabrikRegion,
) -> tuple[str, ...]:
    """Validate raw boundary codes before primary-state recovery is trusted."""

    observed = set(observed_state_codes)
    known = {state.code for state in country.states}
    configured = set(region.required_state_codes)
    if region.primary_state_code is not None:
        configured.add(region.primary_state_code)
    errors: list[str] = []
    if unknown := sorted(observed.difference(known)):
        errors.append(f"source {region.metadata_key} observed unknown states: {', '.join(unknown)}")
    if unexpected := sorted(observed.intersection(known).difference(configured)):
        errors.append(
            f"source {region.metadata_key} observed unexpected states: {', '.join(unexpected)}"
        )
    embedded = configured.difference({region.primary_state_code})
    if missing := sorted(embedded.difference(observed)):
        errors.append(
            f"source {region.metadata_key} did not observe required states: {', '.join(missing)}"
        )
    return tuple(errors)


def accepted_metadata(
    metadata: RemoteMetadata,
    metrics: RecordMetrics,
    *,
    accepted_at: str,
    verified_at: str,
) -> RemoteMetadata:
    """Attach accepted quality evidence to a remote fingerprint."""

    return replace(
        metadata,
        accepted_at=accepted_at,
        verified_at=verified_at,
        record_count=metrics.record_count,
        unique_post_code_count=metrics.unique_post_code_count,
        state_codes=metrics.state_codes,
    )


def region_refresh_result(
    region: GeofabrikRegion,
    status: str,
    metrics: RecordMetrics,
    **evidence: Any,
) -> RegionRefreshResult:
    """Build a region report from validated metrics and run evidence."""

    deltas = evidence.pop("deltas", None)
    return RegionRefreshResult(
        region=region.name,
        status=status,
        records=metrics.record_count,
        country=region.country,
        unique_post_codes=metrics.unique_post_code_count,
        state_codes=metrics.state_codes,
        deltas=asdict(deltas) if deltas is not None else {},
        **evidence,
    )


def country_refresh_result(
    country: CountryConfig,
    evaluation: QualityEvaluation,
    *,
    production: bool,
    warnings: tuple[str, ...] = (),
) -> CountryRefreshResult:
    """Build accepted or rejected country-level report evidence."""

    quality_warnings = evaluation.warnings if production else ()
    return CountryRefreshResult(
        country.slug,
        evaluation.metrics.record_count,
        evaluation.metrics.unique_post_code_count,
        evaluation.metrics.state_codes,
        asdict(evaluation.deltas) if evaluation.deltas else {},
        (*quality_warnings, *warnings),
    )


def combined_country_records(
    paths: Sequence[Path],
    overrides: Mapping[Path, tuple[PostCodeRecord, ...]],
) -> tuple[PostCodeRecord, ...]:
    """Combine persisted and in-memory regional records for one country."""

    return dedupe_records(
        record for path in paths for record in (overrides.get(path) or read_post_code_csv(path))
    )


def write_refresh_report(
    path: Path | None,
    result: RefreshResult,
    error: str = "",
    *,
    error_class: str = "",
) -> None:
    """Persist a secret-free refresh report when a path was requested."""

    if path is None:
        return
    payload = refresh_report_payload(
        result,
        generated_at=iso_timestamp(datetime.now(UTC)),
        error=error,
        error_class=error_class,
    )
    write_json_atomically(path, payload)


def valid_country_baseline(country: CountryConfig, public_root: Path) -> RecordMetrics | None:
    """Return metrics for a valid persisted country output, if available."""

    path = public_country_output_root(public_root, country) / "post_code.csv"
    if not path.exists():
        return None
    try:
        evaluation = validate_country_candidate(read_post_code_csv(path), country=country)
    except (OSError, ValueError):
        return None
    return evaluation.metrics if evaluation.is_valid else None


def load_source_baseline(
    *,
    region: GeofabrikRegion,
    country: CountryConfig,
    metadata: RemoteMetadata | None,
    path: Path,
    generated_at: str,
    now: datetime,
) -> SourceBaseline | None:
    """Load and validate one persisted regional baseline and its provenance."""

    if metadata is None or metadata.url != region.url or not path.exists():
        return None
    if metadata.content_length <= 0 or GEOFABRIK_MD5_PATTERN.fullmatch(metadata.md5) is None:
        return None
    try:
        records = read_post_code_csv(path)
    except (OSError, ValueError):
        return None
    evaluation = validate_source_candidate(records, country=country, region=region)
    metrics = evaluation.metrics
    evidence_matches = (
        metadata.record_count in (None, metrics.record_count)
        and metadata.unique_post_code_count in (None, metrics.unique_post_code_count)
        and (not metadata.state_codes or metadata.state_codes == metrics.state_codes)
    )
    if not evaluation.is_valid or not evidence_matches:
        return None
    try:
        timestamp = validated_provenance_timestamp(
            accepted_at=metadata.accepted_at,
            verified_at=metadata.verified_at,
            generated_at=generated_at,
            now=now,
        )
        provenance_valid = True
    except ValueError:
        timestamp, provenance_valid = "", False
    usable = provenance_valid and bool(timestamp) and is_last_known_good_usable(timestamp, now=now)
    return SourceBaseline(records, metrics, usable, provenance_valid)
