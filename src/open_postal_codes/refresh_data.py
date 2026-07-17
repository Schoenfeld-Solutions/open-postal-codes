"""Refresh public D-A-CH post code files from Geofabrik PBFs."""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import open_postal_codes.countries as country_contracts
import open_postal_codes.post_code as post_code_contracts
from open_postal_codes.countries import (
    GEOFABRIK_MD5_PATTERN,
    MAX_REMOTE_ATTEMPTS,
    RETRY_DELAYS_SECONDS,
    RETRYABLE_HTTP_CODES,
    CandidateRefreshEvidence,
    CountryConfig,
    GeofabrikRegion,
    RemoteMetadata,
    candidate_refresh_evidence,
    configured_countries,
    configured_german_regions,
    configured_selection,
    countries_for_regions,
    default_geofabrik_regions,
    default_german_regions,
    get_country_config,
    source_label,
)
from open_postal_codes.osm_extract import (
    ExtractionError,
    download_region_once,
    existing_download_matches,
    extract_post_codes_from_osm,
)
from open_postal_codes.post_code import (
    MetadataDocumentError,
    PostCodeRecord,
    iso_timestamp,
    load_metadata_document,
    public_country_output_root,
    region_output_path,
    validate_refresh_paths,
    write_refresh_files_transactionally,
)
from open_postal_codes.refresh_quality import (
    AcceptedSource,
    CountryRefreshResult,
    RefreshResult,
    SourceBaseline,
    accepted_metadata,
    build_refresh_result,
    calculate_record_metrics,
    combined_country_records,
    country_refresh_result,
    load_source_baseline,
    refresh_generated_at,
    region_refresh_result,
    source_error_class,
    valid_country_baseline,
    validate_country_candidate,
    validate_observed_state_codes,
    validate_source_candidate,
    write_refresh_report,
)

type ProgressCallback = Callable[[str], None]
default_regions = default_german_regions
IntegrityError = country_contracts.GeofabrikIntegrityError
NetworkError = country_contracts.GeofabrikNetworkError
load_metadata = post_code_contracts.load_metadata
write_metadata = post_code_contracts.write_metadata


class RefreshError(RuntimeError):
    def __init__(self, message: str, *, result: RefreshResult | None = None) -> None:
        super().__init__(message)
        self.result = result


class QualityError(RefreshError):
    pass


def fetch_remote_metadata(region: GeofabrikRegion) -> RemoteMetadata:
    headers = remote_headers(region.url)
    try:
        content_length = int(headers["Content-Length"])
    except (KeyError, ValueError) as error:
        raise IntegrityError(f"{region.url} has no valid Content-Length") from error
    if content_length <= 0:
        raise IntegrityError(f"{region.url} is empty")
    return RemoteMetadata(
        region.url,
        content_length,
        headers.get("ETag", ""),
        headers.get("Last-Modified", ""),
        fetch_remote_md5(region),
    )


def remote_headers(url: str) -> dict[str, str]:
    def request_headers() -> dict[str, str]:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=60) as response:
            return dict(response.headers.items())

    return retry_remote(request_headers, f"required remote file is not available: {url}")


def fetch_remote_md5(region: GeofabrikRegion) -> str:
    def request_checksum() -> str:
        with urllib.request.urlopen(region.md5_url, timeout=60) as response:
            return bytes(response.read()).decode("utf-8", errors="replace")

    text = retry_remote(
        request_checksum, f"required checksum file is not available: {region.md5_url}"
    )
    match = GEOFABRIK_MD5_PATTERN.search(text)
    if match is None:
        raise IntegrityError(f"checksum file does not contain an MD5 digest: {region.md5_url}")
    return match.group("md5").lower()


def retry_remote[T](operation: Callable[[], T], failure_message: str) -> T:
    for attempt in range(MAX_REMOTE_ATTEMPTS):
        try:
            return operation()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if not retryable_remote_error(error) or attempt == MAX_REMOTE_ATTEMPTS - 1:
                raise NetworkError(failure_message) from error
            time.sleep(retry_delay(error, attempt))
    raise AssertionError("unreachable remote retry state")


def retryable_remote_error(error: BaseException) -> bool:
    return not isinstance(error, urllib.error.HTTPError) or error.code in RETRYABLE_HTTP_CODES


def retry_delay(error: BaseException, attempt: int) -> float:
    if isinstance(error, urllib.error.HTTPError) and error.headers:
        value = error.headers.get("Retry-After")
        if value:
            try:
                seconds = float(value)
            except ValueError:
                try:
                    seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
                except (TypeError, ValueError):
                    seconds = RETRY_DELAYS_SECONDS[attempt]
            return min(max(seconds, 0.0), 60.0)
    return RETRY_DELAYS_SECONDS[attempt]


def download_region(
    *, region: GeofabrikRegion, metadata: RemoteMetadata, target_path: Path
) -> RemoteMetadata:
    """Download a PBF with at most three requests and full integrity checks."""
    if existing_download_matches(target_path, metadata):
        return metadata
    current = metadata
    for attempt in range(MAX_REMOTE_ATTEMPTS):
        try:
            download_region_once(region, current, target_path)
            return current
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            target_path.with_suffix(f"{target_path.suffix}.part").unlink(missing_ok=True)
            if not retryable_remote_error(error) or attempt == MAX_REMOTE_ATTEMPTS - 1:
                message = f"required remote file could not be downloaded: {region.url}"
                raise NetworkError(message) from error
            time.sleep(retry_delay(error, attempt))
        except IntegrityError:
            if attempt == MAX_REMOTE_ATTEMPTS - 1:
                raise
            current = fetch_remote_metadata(region)
            time.sleep(RETRY_DELAYS_SECONDS[attempt])
    raise AssertionError("unreachable download retry state")


def refresh_data(
    *,
    download_root: Path,
    metadata_path: Path,
    region_output_root: Path,
    public_output_root: Path,
    regions: tuple[GeofabrikRegion, ...] | None = None,
    countries: tuple[CountryConfig, ...] | None = None,
    progress: ProgressCallback | None = None,
    report_path: Path | None = None,
    now: datetime | None = None,
) -> RefreshResult:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise RefreshError("refresh time must include a UTC offset")
    if (
        regions is not None
        and countries is not None
        and {item.slug for item in countries} != {"de"}
    ):
        raise RefreshError("--regions can only be combined with --countries de")
    selected = regions or default_geofabrik_regions(countries)
    if len(set(selected)) != len(selected) or not set(selected) <= set(default_geofabrik_regions()):
        raise RefreshError("refresh regions must use unique configured source contracts")
    try:
        validate_refresh_paths(
            download_root, metadata_path, region_output_root, public_output_root, report_path
        )
    except ValueError as error:
        raise RefreshError(str(error)) from error
    run = _RefreshRun(
        download_root,
        metadata_path,
        region_output_root,
        public_output_root,
        selected,
        progress,
        report_path,
        current_time.astimezone(UTC),
    )
    return run.execute()


class _RefreshRun:
    def __init__(
        self,
        download_root: Path,
        metadata_path: Path,
        region_root: Path,
        public_root: Path,
        regions: tuple[GeofabrikRegion, ...],
        progress: ProgressCallback | None,
        report_path: Path | None,
        current_time: datetime,
    ) -> None:
        self.download_root = download_root
        self.metadata_path = metadata_path
        self.region_root = region_root
        self.public_root = public_root
        self.regions = regions
        self.countries = countries_for_regions(regions)
        self.progress = progress
        self.report_path = report_path
        self.now = current_time
        self.started = time.monotonic()
        try:
            self.generated_at, self.previous = load_metadata_document(metadata_path)
        except MetadataDocumentError as error:
            raise RefreshError(str(error)) from error
        self.baselines: dict[str, SourceBaseline | None] = {}
        self.observed: dict[str, RemoteMetadata] = {}
        self.accepted: dict[str, AcceptedSource] = {}
        self.source_duration: dict[str, float] = {}

    def execute(self) -> RefreshResult:
        self.emit(
            f"Starting data refresh for {len(self.regions)} sources across "
            f"{','.join(country.slug for country in self.countries) or 'none'}."
        )
        self.baselines = {
            region.metadata_key: self.load_baseline(region) for region in self.regions
        }
        inventory_errors = self.inventory()
        if inventory_errors:
            detail = "\n".join(inventory_errors)
            self.fail(f"remote inventory failed without usable last-known-good data:\n{detail}")
        for index, region in enumerate(self.regions, 1):
            if region.metadata_key not in self.accepted:
                self.refresh_source(index, region)
        country_records, country_results = self.rebuild_countries()
        metadata = dict(self.previous)
        for region in self.regions:
            source = self.accepted[region.metadata_key]
            if source.result.status != "reused_last_good":
                metadata[region.metadata_key] = source.metadata
        try:
            generated_at = refresh_generated_at(
                self.regions, self.accepted, self.generated_at, now=self.now
            )
        except ValueError as error:
            self.fail(str(error), country_results)
            raise AssertionError("unreachable generated_at state") from error
        result = build_refresh_result(
            self.regions,
            self.accepted,
            country_results,
            "success",
            time.monotonic() - self.started,
        )
        write_refresh_report(self.report_path, result)
        self.emit("Promoting validated regional, public, and metadata outputs")
        try:
            write_refresh_files_transactionally(
                metadata_path=self.metadata_path,
                metadata=metadata,
                generated_at=generated_at,
                regional_outputs=tuple(
                    (source.records, region_output_path(self.region_root, region))
                    for region in self.regions
                    if (source := self.accepted[region.metadata_key]).promote
                ),
                public_outputs=tuple(
                    (
                        country_records[country.slug],
                        public_country_output_root(self.public_root, country),
                    )
                    for country in self.countries
                ),
            )
        except (OSError, ValueError) as error:
            self.fail(f"output promotion failed: {error}", country_results, "storage")
        return result

    def inventory(self) -> list[str]:
        errors: list[str] = []
        for index, region in enumerate(self.regions, 1):
            self.emit(f"{source_label(index, len(self.regions), region)}: checking remote metadata")
            started = time.monotonic()
            try:
                self.observed[region.metadata_key] = fetch_remote_metadata(region)
                self.source_duration[region.metadata_key] = time.monotonic() - started
            except (NetworkError, IntegrityError) as error:
                duration = self.source_duration[region.metadata_key] = time.monotonic() - started
                source = self.fallback(region, error, duration)
                self.accepted[region.metadata_key] = source
                if source.result.status == "failed":
                    errors.append(f"{region.country}/{region.name}: {error}")
        if errors:
            for region in self.regions:
                if region.metadata_key not in self.accepted:
                    self.accepted[region.metadata_key] = self.fallback(
                        region,
                        RefreshError("not processed because another source failed inventory"),
                        self.source_duration[region.metadata_key],
                        allow_reuse=False,
                    )
        return errors

    def refresh_source(self, index: int, region: GeofabrikRegion) -> None:
        country = get_country_config(region.country)
        label = source_label(index, len(self.regions), region)
        metadata = self.observed[region.metadata_key]
        previous = self.previous.get(region.metadata_key)
        baseline = self.baselines[region.metadata_key]
        started = time.monotonic() - self.source_duration[region.metadata_key]
        if (
            baseline
            and baseline.provenance_valid
            and previous
            and previous.stable_key() == metadata.stable_key()
        ):
            verified = accepted_metadata(
                metadata,
                baseline.metrics,
                accepted_at=previous.accepted_at or previous.verified_at or self.generated_at,
                verified_at=iso_timestamp(self.now),
            )
            report = region_refresh_result(
                region,
                "unchanged",
                baseline.metrics,
                md5=metadata.md5,
                duration_seconds=round(time.monotonic() - started, 3),
            )
            self.accepted[region.metadata_key] = AcceptedSource(
                baseline.records, verified, report, False
            )
            self.emit(f"{label}: unchanged source with {baseline.metrics.record_count} records")
            return
        try:
            candidate: CandidateRefreshEvidence | None = None
            self.emit(f"{label}: downloading PBF")
            pbf_path = self.download_root / country.slug / f"{region.name}.osm.pbf"
            metadata = download_region(region=region, metadata=metadata, target_path=pbf_path)
            self.emit(f"{label}: extracting post code records")
            extraction = extract_post_codes_from_osm(pbf_path, country=country.code, region=region)
            evaluation = validate_source_candidate(
                extraction.records,
                country=country,
                region=region,
                baseline=baseline.metrics if baseline else None,
            )
            attempted = region_refresh_result(
                region,
                "failed",
                evaluation.metrics,
                observed_state_codes=extraction.observed_state_codes,
                inferred_state_records=extraction.inferred_state_records,
                md5=metadata.md5,
                duration_seconds=round(time.monotonic() - started, 3),
                deltas=evaluation.deltas,
                warnings=evaluation.warnings,
            )
            candidate = candidate_refresh_evidence(attempted)
            errors = (
                *validate_observed_state_codes(
                    extraction.observed_state_codes, country=country, region=region
                ),
                *evaluation.errors,
            )
            if errors:
                raise QualityError("; ".join(errors))
        except (NetworkError, IntegrityError, QualityError, ExtractionError) as error:
            source = self.fallback(region, error, time.monotonic() - started, candidate=candidate)
            self.accepted[region.metadata_key] = source
            if source.result.status == "failed":
                self.fail(
                    f"{country.slug}/{region.name} failed without usable "
                    f"last-known-good data: {error}"
                )
            self.emit(f"{label}: reused validated last-known-good data")
            return
        accepted = accepted_metadata(
            metadata,
            evaluation.metrics,
            accepted_at=iso_timestamp(self.now),
            verified_at=iso_timestamp(self.now),
        )
        report = replace(attempted, status="fresh")
        self.accepted[region.metadata_key] = AcceptedSource(
            extraction.records, accepted, report, True
        )
        self.emit(f"{label}: accepted {evaluation.metrics.record_count} records")

    def load_baseline(self, region: GeofabrikRegion) -> SourceBaseline | None:
        return load_source_baseline(
            region=region,
            country=get_country_config(region.country),
            metadata=self.previous.get(region.metadata_key),
            path=region_output_path(self.region_root, region),
            generated_at=self.generated_at,
            now=self.now,
        )

    def fallback(
        self,
        region: GeofabrikRegion,
        error: BaseException,
        duration: float,
        *,
        candidate: CandidateRefreshEvidence | None = None,
        allow_reuse: bool = True,
    ) -> AcceptedSource:
        country = get_country_config(region.country)
        key = region.metadata_key
        baseline = self.baselines[key]
        metadata = self.previous.get(key)
        fingerprint = metadata if allow_reuse else self.observed.get(key) or metadata
        error_class = source_error_class(error)
        if allow_reuse and baseline and baseline.usable_as_last_good and metadata:
            warning = f"source {region.metadata_key} reused last-known-good data: {error}"
            report = region_refresh_result(
                region,
                "reused_last_good",
                baseline.metrics,
                md5=metadata.md5,
                duration_seconds=round(duration, 3),
                warnings=(warning,),
                error_class=error_class,
                error=str(error),
                candidate=candidate,
            )
            return AcceptedSource(baseline.records, metadata, report, False)
        metrics = baseline.metrics if baseline else calculate_record_metrics((), country=country)
        report = region_refresh_result(
            region,
            "failed",
            metrics,
            md5=fingerprint.md5 if fingerprint else "",
            duration_seconds=round(duration, 3),
            error_class=error_class,
            error=str(error),
            candidate=candidate,
        )
        placeholder = metadata or RemoteMetadata(region.url, 1, "", "", "0" * 32)
        return AcceptedSource(baseline.records if baseline else (), placeholder, report, False)

    def rebuild_countries(
        self,
    ) -> tuple[dict[str, tuple[PostCodeRecord, ...]], tuple[CountryRefreshResult, ...]]:
        overrides = {
            region_output_path(self.region_root, region): self.accepted[region.metadata_key].records
            for region in self.regions
        }
        outputs: dict[str, tuple[PostCodeRecord, ...]] = {}
        results: list[CountryRefreshResult] = []
        for country in self.countries:
            self.emit(f"Rebuilding public {country.slug} output from selected sources")
            production = configured_selection(country, self.regions)
            expected = tuple(
                region_output_path(self.region_root, item) for item in country.geofabrik_regions
            )
            selected = tuple(path for path in overrides if path.parent.parent.name == country.slug)
            paths = expected if production else selected
            missing = [path for path in paths if path not in overrides and not path.exists()]
            if production and missing:
                names = ", ".join(path.name for path in missing)
                self.fail(f"{country.slug} is missing regional outputs: {names}")
            records = combined_country_records(paths, overrides)
            if not records:
                self.fail(f"{country.slug} regional outputs produced zero public records")
            baseline = valid_country_baseline(country, self.public_root) if production else None
            evaluation = validate_country_candidate(records, country=country, baseline=baseline)
            candidate_result = country_refresh_result(country, evaluation, production=production)
            if production and not evaluation.is_valid:
                message = "; ".join(evaluation.errors)
                if not self.reuse_country_last_good(country, message):
                    self.fail(message, (*results, candidate_result), "quality")
                overrides.update(
                    {
                        region_output_path(self.region_root, region): self.accepted[
                            region.metadata_key
                        ].records
                        for region in self.regions
                        if region.country == country.slug
                    }
                )
                records = combined_country_records(paths, overrides)
                evaluation = validate_country_candidate(records, country=country, baseline=baseline)
                if not evaluation.is_valid:
                    self.fail("; ".join(evaluation.errors), (*results, candidate_result), "quality")
                fallback_warning = tuple([f"country {country.slug} rejected: {message}"])
            else:
                fallback_warning = ()
            outputs[country.slug] = records
            results.append(
                country_refresh_result(
                    country, evaluation, production=production, warnings=fallback_warning
                )
            )
        return outputs, tuple(results)

    def reuse_country_last_good(self, country: CountryConfig, message: str) -> bool:
        fresh = tuple(
            region
            for region in self.regions
            if region.country == country.slug
            and self.accepted[region.metadata_key].result.status == "fresh"
        )
        for region in fresh:
            source = self.accepted[region.metadata_key]
            self.accepted[region.metadata_key] = self.fallback(
                region,
                QualityError(message),
                source.result.duration_seconds,
                candidate=candidate_refresh_evidence(source.result),
            )
        return bool(fresh) and all(
            self.accepted[region.metadata_key].result.status == "reused_last_good"
            for region in fresh
        )

    def fail(
        self,
        message: str,
        country_results: tuple[CountryRefreshResult, ...] = (),
        error_class: str = "refresh",
    ) -> None:
        result = build_refresh_result(
            self.regions,
            self.accepted,
            country_results,
            "failed",
            time.monotonic() - self.started,
        )
        write_refresh_report(self.report_path, result, error=message, error_class=error_class)
        raise RefreshError(message, result=result)

    def emit(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)


def parse_regions(value: str | None) -> tuple[GeofabrikRegion, ...] | None:
    try:
        return configured_german_regions(value)
    except ValueError as error:
        raise RefreshError(str(error)) from error


def parse_countries(value: str | None) -> tuple[CountryConfig, ...] | None:
    try:
        return configured_countries(value)
    except ValueError as error:
        raise RefreshError(str(error)) from error


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument(
        "--metadata-path",
        type=Path,
        default=Path("data/sources/geofabrik-regions.json"),
    )
    parser.add_argument("--region-output-root", type=Path, default=Path("data/regional/v1"))
    parser.add_argument("--public-output-root", type=Path, default=Path("data/public/v1"))
    parser.add_argument("--report-path", type=Path)
    parser.add_argument("--countries", help="Comma-separated country slugs or ISO codes")
    parser.add_argument("--regions", help="Comma-separated German regions for smoke runs")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed = parse_arguments(arguments)
    regions = parse_regions(parsed.regions)
    countries = parse_countries(parsed.countries)
    if regions is not None and countries is None:
        countries = (get_country_config("de"),)
    try:
        result = refresh_data(
            download_root=parsed.download_root,
            metadata_path=parsed.metadata_path,
            region_output_root=parsed.region_output_root,
            public_output_root=parsed.public_output_root,
            regions=regions,
            countries=countries,
            progress=lambda message: print(message, flush=True),
            report_path=parsed.report_path,
        )
    except RefreshError as error:
        if error.result is None:
            write_refresh_report(
                parsed.report_path,
                RefreshResult((), 0, status="failed"),
                str(error),
                error_class="refresh",
            )
        print(f"Data refresh failed: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        write_refresh_report(
            parsed.report_path,
            RefreshResult((), 0, status="failed"),
            str(error),
            error_class="unexpected",
        )
        raise
    print(country_contracts.refresh_completion_message(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
