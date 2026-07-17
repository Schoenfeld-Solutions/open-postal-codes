"""Unit tests for refresh candidate quality guardrails."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TypedDict

import pytest

import open_postal_codes.refresh_data as refresh_module
from open_postal_codes.countries import (
    CountryConfig,
    GeofabrikNetworkError,
    GeofabrikRegion,
    RemoteMetadata,
    get_country_config,
)
from open_postal_codes.post_code import (
    PostCodeRecord,
    replace_files_transactionally,
    write_metadata,
    write_post_code_csv,
)
from open_postal_codes.refresh_data import RefreshError, refresh_data
from open_postal_codes.refresh_quality import (
    RefreshResult,
    calculate_record_metrics,
    is_last_known_good_usable,
    validate_country_candidate,
    validate_observed_state_codes,
    validate_source_candidate,
    write_refresh_report,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)
BASELINE_MD5 = "11111111111111111111111111111111"
CANDIDATE_MD5 = "22222222222222222222222222222222"


class _RefreshPaths(TypedDict):
    download_root: Path
    metadata_path: Path
    region_output_root: Path
    public_output_root: Path


def _records(
    country: CountryConfig,
    *,
    record_count: int,
    unique_post_code_count: int,
    states: Sequence[str] | None = None,
) -> tuple[PostCodeRecord, ...]:
    selected_states = states or tuple(state.name for state in country.states)
    width = 5 if country.code == "DE" else 4
    offset = 10_000 if country.code == "DE" else 1_000
    return tuple(
        PostCodeRecord(
            code=f"{offset + (index % unique_post_code_count):0{width}d}",
            city=f"City {index}",
            country=country.code,
            state=selected_states[index % len(selected_states)],
            time_zone=country.time_zone,
        )
        for index in range(record_count)
    )


def _region(country: CountryConfig, name: str) -> GeofabrikRegion:
    return next(region for region in country.geofabrik_regions if region.name == name)


def _paths(root: Path) -> _RefreshPaths:
    return {
        "download_root": root / "downloads",
        "metadata_path": root / "metadata.json",
        "region_output_root": root / "regional",
        "public_output_root": root / "public",
    }


def _metadata(
    region: GeofabrikRegion,
    records: Sequence[PostCodeRecord],
    timestamp: str,
    *,
    md5: str = BASELINE_MD5,
) -> RemoteMetadata:
    metrics = calculate_record_metrics(records, country=get_country_config(region.country))
    return RemoteMetadata(
        region.url,
        3,
        md5,
        timestamp,
        md5,
        accepted_at=timestamp,
        verified_at=timestamp,
        record_count=metrics.record_count,
        unique_post_code_count=metrics.unique_post_code_count,
        state_codes=metrics.state_codes,
    )


def _regional_path(paths: _RefreshPaths, region: GeofabrikRegion) -> Path:
    return paths["region_output_root"] / region.country / "post_code" / region.output_name


def _install_candidate(
    monkeypatch: pytest.MonkeyPatch,
    region: GeofabrikRegion,
    records: Sequence[PostCodeRecord],
    *,
    metadata: RemoteMetadata,
) -> None:
    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", lambda _: metadata)
    monkeypatch.setattr(refresh_module, "download_region", lambda **_: metadata)
    monkeypatch.setattr(
        refresh_module,
        "extract_post_codes_from_osm",
        lambda *_args, **_kwargs: SimpleNamespace(
            records=tuple(records),
            observed_state_codes=region.required_state_codes,
            inferred_state_records=0,
        ),
    )


def test_calculate_record_metrics_uses_canonical_state_codes() -> None:
    country = get_country_config("DE")
    records = (
        PostCodeRecord(code="28195", city="Bremen", state="Bremen"),
        PostCodeRecord(code="28195", city="Bremen Altstadt", state="Bremen"),
        PostCodeRecord(code="10115", city="Berlin", state="Berlin"),
    )

    metrics = calculate_record_metrics(records, country=country)

    assert metrics.record_count == 3
    assert metrics.unique_post_code_count == 2
    assert metrics.state_codes == ("DE-BE", "DE-HB")
    assert metrics.state_record_count("DE-HB") == 2
    assert metrics.state_record_count("DE-BB") == 0


def test_source_candidate_requires_primary_and_embedded_states() -> None:
    country = get_country_config("DE")
    region = _region(country, "brandenburg")
    records = (
        PostCodeRecord(code="10115", city="Berlin", state="Berlin"),
        PostCodeRecord(code="14467", city="Potsdam", state="Brandenburg"),
    )

    result = validate_source_candidate(records, country=country, region=region)

    assert result.is_valid
    assert result.errors == ()
    assert result.metrics.state_codes == ("DE-BE", "DE-BB")


def test_source_candidate_rejects_missing_brandenburg_primary_state() -> None:
    country = get_country_config("DE")
    region = _region(country, "brandenburg")
    records = (PostCodeRecord(code="10115", city="Berlin", state="Berlin"),)

    result = validate_source_candidate(records, country=country, region=region)

    assert not result.is_valid
    assert result.errors == ("source brandenburg has no records for primary state DE-BB",)


def test_source_candidate_rejects_empty_unknown_and_wrong_country_states() -> None:
    country = get_country_config("DE")
    region = _region(country, "bremen")
    records = (
        PostCodeRecord(code="28195", city="Bremen", state=""),
        PostCodeRecord(code="28197", city="Bremen", state="Atlantis"),
        PostCodeRecord(code="1010", city="Wien", country="AT", state="Wien"),
    )

    result = validate_source_candidate(records, country=country, region=region)

    assert "source bremen has 1 records without state" in result.errors
    assert "source bremen has unknown state names: Atlantis, Wien" in result.errors
    assert "source bremen has 1 records outside country DE" in result.errors
    assert "source bremen has no records for primary state DE-HB" in result.errors


def test_source_candidate_rejects_known_state_outside_source_contract() -> None:
    country = get_country_config("DE")
    region = _region(country, "bremen")
    records = (
        PostCodeRecord(code="28195", city="Bremen", state="Bremen"),
        PostCodeRecord(code="10115", city="Berlin", state="Berlin"),
    )

    result = validate_source_candidate(records, country=country, region=region)

    assert result.errors == ("source bremen has unexpected states: DE-BE",)


def test_brandenburg_observed_states_allow_missing_primary_boundary() -> None:
    country = get_country_config("DE")
    region = _region(country, "brandenburg")

    errors = validate_observed_state_codes(("DE-BE",), country=country, region=region)

    assert errors == ()


def test_brandenburg_observed_states_require_embedded_berlin() -> None:
    country = get_country_config("DE")
    region = _region(country, "brandenburg")

    errors = validate_observed_state_codes(("DE-BB",), country=country, region=region)

    assert errors == ("source brandenburg did not observe required states: DE-BE",)


def test_observed_states_reject_unknown_and_unexpected_codes() -> None:
    country = get_country_config("DE")
    region = _region(country, "bremen")

    errors = validate_observed_state_codes(
        ("DE-HB", "DE-BE", "DE-XX"), country=country, region=region
    )

    assert errors == (
        "source bremen observed unknown states: DE-XX",
        "source bremen observed unexpected states: DE-BE",
    )


def test_country_extract_observes_every_configured_state() -> None:
    country = get_country_config("AT")
    region = _region(country, "austria")
    observed = tuple(state.code for state in country.states if state.code != "AT-1")

    errors = validate_observed_state_codes(observed, country=country, region=region)

    assert errors == ("source at/austria did not observe required states: AT-1",)


def test_source_delta_limits_warn_at_half_and_fail_above_maximum() -> None:
    country = get_country_config("DE")
    region = _region(country, "bremen")
    baseline_records = _records(
        country,
        record_count=100,
        unique_post_code_count=100,
        states=("Bremen",),
    )
    baseline = calculate_record_metrics(baseline_records, country=country)

    warning = validate_source_candidate(
        _records(
            country,
            record_count=92,
            unique_post_code_count=92,
            states=("Bremen",),
        ),
        country=country,
        region=region,
        baseline=baseline,
    )
    failure = validate_source_candidate(
        _records(
            country,
            record_count=84,
            unique_post_code_count=84,
            states=("Bremen",),
        ),
        country=country,
        region=region,
        baseline=baseline,
    )

    assert warning.is_valid
    assert any("lost 8.0% of records" in message for message in warning.warnings)
    assert any("lost 8.0% of unique post codes" in message for message in warning.warnings)
    assert failure.deltas is not None
    assert failure.deltas.record_count_ratio == pytest.approx(-0.16)
    assert any("maximum loss is 15.0%" in message for message in failure.errors)
    assert any("maximum loss is 12.0%" in message for message in failure.errors)


def test_source_growth_limit_applies_to_records_and_unique_post_codes() -> None:
    country = get_country_config("DE")
    region = _region(country, "bremen")
    baseline = calculate_record_metrics(
        _records(
            country,
            record_count=100,
            unique_post_code_count=100,
            states=("Bremen",),
        ),
        country=country,
    )

    result = validate_source_candidate(
        _records(
            country,
            record_count=126,
            unique_post_code_count=126,
            states=("Bremen",),
        ),
        country=country,
        region=region,
        baseline=baseline,
    )

    assert sum("maximum growth is 25.0%" in error for error in result.errors) == 2


def test_austria_2979_records_with_all_states_and_2000_codes_passes() -> None:
    country = get_country_config("AT")
    records = _records(country, record_count=2_979, unique_post_code_count=2_000)

    result = validate_country_candidate(records, country=country)

    assert result.is_valid
    assert result.metrics.record_count == 2_979
    assert result.metrics.unique_post_code_count == 2_000
    assert result.metrics.state_codes == tuple(state.code for state in country.states)
    assert result.warnings == ("country at has 2000 unique post codes, within 5% of minimum 2000",)


def test_country_candidate_requires_every_configured_state() -> None:
    country = get_country_config("AT")
    records = _records(
        country,
        record_count=2_979,
        unique_post_code_count=2_000,
        states=("Wien",),
    )

    result = validate_country_candidate(records, country=country)

    assert not result.is_valid
    assert any(
        error.startswith("country at is missing expected states:") for error in result.errors
    )
    assert "AT-9" not in next(
        error
        for error in result.errors
        if error.startswith("country at is missing expected states:")
    )


def test_country_unique_post_code_delta_fails_above_five_percent() -> None:
    country = get_country_config("AT")
    baseline = calculate_record_metrics(
        _records(country, record_count=4_000, unique_post_code_count=3_000),
        country=country,
    )
    records = _records(country, record_count=3_600, unique_post_code_count=2_849)

    result = validate_country_candidate(records, country=country, baseline=baseline)

    assert any("maximum loss is 5.0%" in error for error in result.errors)
    assert not any("maximum loss is 10.0%" in error for error in result.errors)
    assert any("lost 10.0% of records" in warning for warning in result.warnings)


def test_last_known_good_is_usable_through_exactly_twenty_one_days() -> None:
    now = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    assert is_last_known_good_usable("2026-07-01T12:00:00Z", now=now)
    assert not is_last_known_good_usable("2026-07-01T11:59:59Z", now=now)


@pytest.mark.parametrize(
    "accepted_at, now, expected_message",
    [
        (
            "not-a-timestamp",
            datetime(2026, 7, 22, tzinfo=UTC),
            "valid ISO 8601 timestamp",
        ),
        (
            "2026-07-01T00:00:00",
            datetime(2026, 7, 22, tzinfo=UTC),
            "must include a UTC offset",
        ),
        (
            "2026-07-23T00:00:00Z",
            datetime(2026, 7, 22, tzinfo=UTC),
            "must not be in the future",
        ),
    ],
)
def test_last_known_good_rejects_invalid_timestamps(
    accepted_at: str,
    now: datetime,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        is_last_known_good_usable(accepted_at, now=now)


def test_last_known_good_rejects_negative_age_budget() -> None:
    with pytest.raises(ValueError, match="maximum_age must not be negative"):
        is_last_known_good_usable(
            "2026-07-01T00:00:00Z",
            now=datetime(2026, 7, 1, tzinfo=UTC),
            maximum_age=-timedelta(seconds=1),
        )


@pytest.mark.parametrize(("age_days", "succeeds"), [(20, True), (22, False)])
def test_country_delta_uses_only_unexpired_source_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    age_days: int,
    succeeds: bool,
) -> None:
    country = get_country_config("AT")
    region = _region(country, "austria")
    baseline = _records(country, record_count=3_000, unique_post_code_count=2_200)
    candidate = _records(country, record_count=3_000, unique_post_code_count=2_070)
    timestamp = (NOW - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    paths = _paths(tmp_path)
    regional = _regional_path(paths, region)
    public = paths["public_output_root"] / "at/post_code.csv"
    write_post_code_csv(baseline, regional)
    write_post_code_csv(baseline, public)
    accepted = _metadata(region, baseline, timestamp)
    write_metadata(paths["metadata_path"], {region.metadata_key: accepted}, generated_at=timestamp)
    before = {path: path.read_bytes() for path in (regional, public, paths["metadata_path"])}
    remote = _metadata(region, candidate, timestamp, md5=CANDIDATE_MD5)
    _install_candidate(monkeypatch, region, candidate, metadata=remote)
    report_path = tmp_path / "refresh-report.json"

    if succeeds:
        result = refresh_data(**paths, regions=(region,), report_path=report_path, now=NOW)
        assert result.regions[0].status == "reused_last_good"
    else:
        with pytest.raises(RefreshError, match="maximum loss is 5.0%"):
            refresh_data(**paths, regions=(region,), report_path=report_path, now=NOW)
    assert {path: path.read_bytes() for path in before} == before
    source = json.loads(report_path.read_text(encoding="utf-8"))["sources"][0]
    assert source["md5"] == BASELINE_MD5
    assert source["candidate"]["md5"] == CANDIDATE_MD5
    assert source["candidate"]["records"] == 3_000
    assert source["candidate"]["unique_post_codes"] == 2_070
    assert source["candidate"]["deltas"]["unique_post_code_count_ratio"] == pytest.approx(
        -130 / 2_200
    )


@pytest.mark.parametrize(
    ("accepted_at", "verified_at"),
    [
        ("invalid", "2026-07-16T12:00:00Z"),
        ("2026-07-18T12:00:00Z", "2026-07-16T12:00:00Z"),
        ("2026-07-16T12:00:00Z", "2026-07-15T12:00:00Z"),
    ],
)
def test_invalid_source_provenance_disables_network_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    accepted_at: str,
    verified_at: str,
) -> None:
    country = get_country_config("DE")
    region = _region(country, "bremen")
    records = _records(country, record_count=1, unique_post_code_count=1, states=("Bremen",))
    paths = _paths(tmp_path)
    regional = _regional_path(paths, region)
    write_post_code_csv(records, regional)
    metadata = _metadata(region, records, verified_at)
    metadata = RemoteMetadata(**{**vars(metadata), "accepted_at": accepted_at})
    write_metadata(
        paths["metadata_path"],
        {region.metadata_key: metadata},
        generated_at="2026-07-01T00:00:00Z",
    )
    before = (regional.read_bytes(), paths["metadata_path"].read_bytes())
    monkeypatch.setattr(
        refresh_module,
        "fetch_remote_metadata",
        lambda _: (_ for _ in ()).throw(GeofabrikNetworkError("offline")),
    )

    with pytest.raises(RefreshError, match="without usable last-known-good"):
        refresh_data(**paths, regions=(region,), now=NOW)
    assert (regional.read_bytes(), paths["metadata_path"].read_bytes()) == before
    assert not paths["public_output_root"].exists()


def test_invalid_global_timestamp_blocks_scoped_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    country = get_country_config("DE")
    region = _region(country, "bremen")
    records = _records(country, record_count=1, unique_post_code_count=1, states=("Bremen",))
    paths = _paths(tmp_path)
    write_metadata(paths["metadata_path"], {}, generated_at="invalid")
    before = paths["metadata_path"].read_bytes()
    _install_candidate(
        monkeypatch,
        region,
        records,
        metadata=_metadata(region, records, "2026-07-16T12:00:00Z", md5=CANDIDATE_MD5),
    )
    monkeypatch.setattr(refresh_module, "configured_selection", lambda *_: False)

    with pytest.raises(RefreshError):
        refresh_data(**paths, regions=(region,), now=NOW)
    assert paths["metadata_path"].read_bytes() == before
    assert not paths["region_output_root"].exists()
    assert not paths["public_output_root"].exists()


@pytest.mark.parametrize(
    "overlap",
    ("report_metadata", "report_public", "download_regional", "download_public"),
)
def test_refresh_rejects_overlapping_paths_before_remote_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overlap: str
) -> None:
    paths = _paths(tmp_path)
    report: Path | None = None
    if overlap == "report_metadata":
        report = paths["metadata_path"]
    elif overlap == "report_public":
        report = paths["public_output_root"] / "report.json"
    elif overlap == "download_regional":
        paths["download_root"] = paths["region_output_root"] / "downloads"
    else:
        paths["download_root"] = paths["public_output_root"] / "downloads"
    monkeypatch.setattr(
        refresh_module,
        "fetch_remote_metadata",
        lambda _: (_ for _ in ()).throw(AssertionError("remote access must not start")),
    )

    with pytest.raises(RefreshError):
        refresh_data(
            **paths,
            regions=(_region(get_country_config("DE"), "bremen"),),
            report_path=report,
            now=NOW,
        )
    assert not paths["metadata_path"].exists()


def test_transaction_rejects_duplicate_targets_before_writing(tmp_path: Path) -> None:
    target = tmp_path / "target"
    duplicate = tmp_path / "nested" / ".." / "target"
    first, second = tmp_path / "first", tmp_path / "second"
    target.write_bytes(b"old")
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    with pytest.raises(ValueError, match="duplicate target"):
        replace_files_transactionally(((first, target), (second, duplicate)), tmp_path / "backups")
    assert (target.read_bytes(), first.read_bytes(), second.read_bytes()) == (
        b"old",
        b"first",
        b"second",
    )
    assert not (tmp_path / "backups").exists()


def test_cli_preserves_specific_error_class_from_refresh_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "report.json"
    result = RefreshResult((), 0, status="failed")

    def fail_refresh(**kwargs: Any) -> RefreshResult:
        write_refresh_report(kwargs["report_path"], result, "country gate", error_class="quality")
        raise RefreshError("country gate", result=result)

    monkeypatch.setattr(refresh_module, "refresh_data", fail_refresh)

    assert (
        refresh_module.main(
            ["--download-root", str(tmp_path / "downloads"), "--report-path", str(report_path)]
        )
        == 1
    )
    assert json.loads(report_path.read_text(encoding="utf-8"))["error_class"] == "quality"
