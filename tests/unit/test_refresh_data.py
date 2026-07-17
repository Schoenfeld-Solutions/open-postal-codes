from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TypedDict

import pytest

import open_postal_codes.refresh_data as refresh_module
from open_postal_codes.countries import (
    GeofabrikNetworkError,
    GeofabrikRegion,
    RemoteMetadata,
    get_country_config,
)
from open_postal_codes.post_code import PostCodeRecord, write_post_code_csv
from open_postal_codes.refresh_data import (
    RefreshError,
    default_regions,
    load_metadata,
    parse_arguments,
    parse_countries,
    parse_regions,
    refresh_data,
    write_metadata,
)
from open_postal_codes.refresh_quality import (
    CountryRefreshResult,
    RefreshResult,
    RegionRefreshResult,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)
MD5 = "900150983cd24fb0d6963f7d28e17f72"


class RefreshPaths(TypedDict):
    download_root: Path
    metadata_path: Path
    region_output_root: Path
    public_output_root: Path


def configured_region(name: str, country: str = "de") -> GeofabrikRegion:
    return next(
        region for region in get_country_config(country).geofabrik_regions if region.name == name
    )


def metadata_for(
    region: GeofabrikRegion,
    *,
    etag: str = "v1",
    accepted_at: str = "",
    verified_at: str = "",
    record_count: int | None = None,
    unique_post_code_count: int | None = None,
    state_codes: tuple[str, ...] = (),
) -> RemoteMetadata:
    return RemoteMetadata(
        url=region.url,
        content_length=3,
        etag=etag,
        last_modified="today",
        md5=MD5,
        accepted_at=accepted_at,
        verified_at=verified_at,
        record_count=record_count,
        unique_post_code_count=unique_post_code_count,
        state_codes=state_codes,
    )


def records_for(region: GeofabrikRegion) -> tuple[PostCodeRecord, ...]:
    country = get_country_config(region.country)
    states = {state.code: state.name for state in country.states}
    width_base = 10_000 if country.code == "DE" else 1_000
    return tuple(
        PostCodeRecord(
            code=str(width_base + index),
            city=f"City {index}",
            country=country.code,
            state=states[state_code],
        )
        for index, state_code in enumerate(region.required_state_codes)
    )


def install_fresh_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    records_by_region: dict[str, tuple[PostCodeRecord, ...]] | None = None,
    observed_by_region: dict[str, tuple[str, ...]] | None = None,
    inferred_by_region: dict[str, int] | None = None,
    scoped_source_only: bool = True,
) -> None:
    records_by_region = records_by_region or {}
    observed_by_region = observed_by_region or {}
    inferred_by_region = inferred_by_region or {}
    monkeypatch.setattr(
        refresh_module,
        "fetch_remote_metadata",
        lambda region: metadata_for(region),
    )
    monkeypatch.setattr(
        refresh_module,
        "download_region",
        lambda **kwargs: kwargs["metadata"],
    )

    def fake_extract(
        _input_path: Path,
        *,
        country: str,
        region: GeofabrikRegion,
    ) -> SimpleNamespace:
        del country
        return SimpleNamespace(
            records=records_by_region.get(region.metadata_key, records_for(region)),
            observed_state_codes=observed_by_region.get(
                region.metadata_key, region.required_state_codes
            ),
            inferred_state_records=inferred_by_region.get(region.metadata_key, 0),
        )

    monkeypatch.setattr(refresh_module, "extract_post_codes_from_osm", fake_extract)
    if scoped_source_only:
        monkeypatch.setattr(refresh_module, "configured_selection", lambda *_: False)


def refresh_paths(tmp_path: Path) -> RefreshPaths:
    return {
        "download_root": tmp_path / "downloads",
        "metadata_path": tmp_path / "metadata.json",
        "region_output_root": tmp_path / "regions",
        "public_output_root": tmp_path / "public",
    }


def seed_full_refresh_timestamp(paths: RefreshPaths) -> None:
    write_metadata(
        paths["metadata_path"],
        {},
        generated_at="2026-07-01T00:00:00Z",
    )


def test_default_regions_use_configured_geofabrik_contracts() -> None:
    regions = default_regions()

    assert tuple(region.name for region in regions) == (
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
    assert all(region.primary_state_code for region in regions)
    assert all(region.primary_state_code in region.required_state_codes for region in regions)
    assert configured_region("brandenburg").required_state_codes == ("DE-BB", "DE-BE")
    assert configured_region("niedersachsen").required_state_codes == ("DE-NI", "DE-HB")


def test_parse_countries_selects_dach_geofabrik_sources() -> None:
    countries = parse_countries("de,at,ch")

    assert countries == (
        get_country_config("DE"),
        get_country_config("AT"),
        get_country_config("CH"),
    )
    assert countries[1].geofabrik_regions[0].name == "austria"
    assert countries[2].geofabrik_regions[0].name == "switzerland"


def test_parse_regions_rejects_unknown_names() -> None:
    with pytest.raises(RefreshError, match="unknown"):
        parse_regions("bremen,unknown")


def test_parse_regions_empty_value_uses_default_region_set() -> None:
    assert parse_regions("") is None


def test_metadata_roundtrip_preserves_quality_evidence(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    region = configured_region("bremen")
    metadata = metadata_for(
        region,
        accepted_at="2026-07-16T12:00:00Z",
        verified_at="2026-07-17T12:00:00Z",
        record_count=1,
        unique_post_code_count=1,
        state_codes=("DE-HB",),
    )

    write_metadata(path, {region.metadata_key: metadata}, generated_at="2026-07-17T12:00:00Z")

    loaded = load_metadata(path)[region.metadata_key]
    assert loaded == metadata
    encoded = json.loads(path.read_text(encoding="utf-8"))["regions"][region.metadata_key]
    assert encoded["record_count"] == 1
    assert encoded["unique_post_code_count"] == 1
    assert "records" not in encoded
    assert "unique_post_codes" not in encoded


def test_load_metadata_migrates_legacy_quality_field_names(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-01T00:00:00Z",
                "regions": {
                    "bremen": {
                        "url": configured_region("bremen").url,
                        "content_length": 3,
                        "md5": MD5,
                        "accepted_at": "2026-07-01T00:00:00Z",
                        "records": 2,
                        "unique_post_codes": 1,
                        "state_codes": ["DE-HB"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_metadata(path)["bremen"]
    assert loaded.record_count == 2
    assert loaded.unique_post_code_count == 1
    assert loaded.state_codes == ("DE-HB",)


def test_refresh_data_accepts_fresh_source_and_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = configured_region("sachsen-anhalt")
    records = records_for(region)
    install_fresh_fakes(
        monkeypatch,
        inferred_by_region={region.metadata_key: 252},
        observed_by_region={region.metadata_key: ()},
    )
    paths = refresh_paths(tmp_path)
    seed_full_refresh_timestamp(paths)
    report_path = tmp_path / "diagnostics" / "refresh.json"

    result = refresh_data(
        **paths,
        regions=(region,),
        report_path=report_path,
        now=NOW,
    )

    source = result.regions[0]
    assert source.status == "fresh"
    assert source.records == len(records)
    assert source.state_codes == ("DE-ST",)
    assert source.observed_state_codes == ()
    assert source.inferred_state_records == 252
    accepted = load_metadata(tmp_path / "metadata.json")[region.metadata_key]
    assert accepted.accepted_at == "2026-07-17T12:00:00Z"
    assert accepted.verified_at == "2026-07-17T12:00:00Z"
    assert accepted.record_count == len(records)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "success"
    assert report["sources"][0]["status"] == "fresh"
    assert report["sources"][0]["md5"] == MD5
    assert report["sources"][0]["inferred_state_records"] == 252
    assert "url" not in report["sources"][0]


def test_refresh_data_writes_country_scoped_outputs_for_at_and_ch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    austria = configured_region("austria", "at")
    switzerland = configured_region("switzerland", "ch")
    install_fresh_fakes(monkeypatch)
    paths = refresh_paths(tmp_path)
    seed_full_refresh_timestamp(paths)

    result = refresh_data(
        **paths,
        regions=(austria, switzerland),
        now=NOW,
    )

    assert result.public_records == 35
    assert tuple(country.country for country in result.countries) == ("at", "ch")
    assert {source.status for source in result.regions} == {"fresh"}
    assert (tmp_path / "regions/at/post_code/austria.csv").exists()
    assert (tmp_path / "regions/ch/post_code/switzerland.csv").exists()
    assert (tmp_path / "public/at/post_code.json").exists()
    assert (tmp_path / "public/ch/post_code.xml").exists()


def test_refresh_data_marks_valid_unchanged_source_and_only_advances_verified_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = configured_region("bremen")
    records = records_for(region)
    accepted_at = "2026-07-10T12:00:00Z"
    metadata = metadata_for(
        region,
        accepted_at=accepted_at,
        verified_at=accepted_at,
        record_count=1,
        unique_post_code_count=1,
        state_codes=("DE-HB",),
    )
    paths = refresh_paths(tmp_path)
    write_metadata(
        paths["metadata_path"],
        {region.metadata_key: metadata},
        generated_at=accepted_at,
    )
    write_post_code_csv(records, paths["region_output_root"] / "de/post_code/bremen.csv")
    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", lambda _: metadata)
    monkeypatch.setattr(refresh_module, "configured_selection", lambda *_: False)

    result = refresh_data(**paths, regions=(region,), now=NOW)

    assert result.regions[0].status == "unchanged"
    updated = load_metadata(paths["metadata_path"])[region.metadata_key]
    assert updated.accepted_at == accepted_at
    assert updated.verified_at == "2026-07-17T12:00:00Z"


def test_network_failure_reuses_last_good_at_exactly_21_days(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = configured_region("bremen")
    timestamp = (NOW - timedelta(days=21)).isoformat().replace("+00:00", "Z")
    metadata = metadata_for(
        region,
        accepted_at=timestamp,
        verified_at=timestamp,
        record_count=1,
        unique_post_code_count=1,
        state_codes=("DE-HB",),
    )
    paths = refresh_paths(tmp_path)
    write_metadata(paths["metadata_path"], {region.metadata_key: metadata}, generated_at=timestamp)
    write_post_code_csv(
        records_for(region), paths["region_output_root"] / "de/post_code/bremen.csv"
    )
    monkeypatch.setattr(
        refresh_module,
        "fetch_remote_metadata",
        lambda _: (_ for _ in ()).throw(GeofabrikNetworkError("offline")),
    )
    monkeypatch.setattr(refresh_module, "configured_selection", lambda *_: False)

    result = refresh_data(**paths, regions=(region,), now=NOW)

    assert result.regions[0].status == "reused_last_good"
    assert load_metadata(paths["metadata_path"])[region.metadata_key] == metadata


@pytest.mark.parametrize("invalid_kind", ["stale", "structural"])
def test_network_failure_rejects_invalid_baseline_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_kind: str,
) -> None:
    region = configured_region("bremen")
    timestamp = (
        (NOW - timedelta(days=22) if invalid_kind == "stale" else NOW - timedelta(days=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    metadata = metadata_for(region, accepted_at=timestamp, verified_at=timestamp)
    paths = refresh_paths(tmp_path)
    write_metadata(paths["metadata_path"], {region.metadata_key: metadata}, generated_at=timestamp)
    baseline = (
        records_for(region)
        if invalid_kind == "stale"
        else (PostCodeRecord(code="28195", city="Bremen", state=""),)
    )
    regional_path = paths["region_output_root"] / "de/post_code/bremen.csv"
    write_post_code_csv(baseline, regional_path)
    before_metadata = paths["metadata_path"].read_bytes()
    before_regional = regional_path.read_bytes()
    monkeypatch.setattr(
        refresh_module,
        "fetch_remote_metadata",
        lambda _: (_ for _ in ()).throw(GeofabrikNetworkError("offline")),
    )

    with pytest.raises(RefreshError, match="without usable last-known-good"):
        refresh_data(**paths, regions=(region,), now=NOW)

    assert paths["metadata_path"].read_bytes() == before_metadata
    assert regional_path.read_bytes() == before_regional
    assert not paths["public_output_root"].exists()


def test_observed_unknown_state_rejects_candidate_and_reports_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = configured_region("bremen")
    install_fresh_fakes(
        monkeypatch,
        observed_by_region={region.metadata_key: ("DE-XX",)},
    )
    report_path = tmp_path / "report.json"

    with pytest.raises(RefreshError, match="observed unknown states"):
        refresh_data(
            **refresh_paths(tmp_path),
            regions=(region,),
            report_path=report_path,
            now=NOW,
        )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["sources"][0]["status"] == "failed"
    assert report["sources"][0]["error_class"] == "quality"
    assert not (tmp_path / "regions/de/post_code/bremen.csv").exists()
    assert not (tmp_path / "metadata.json").exists()


def test_scoped_configured_refresh_requires_other_committed_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = configured_region("bremen")
    install_fresh_fakes(monkeypatch, scoped_source_only=False)

    with pytest.raises(RefreshError, match="missing regional outputs"):
        refresh_data(**refresh_paths(tmp_path), regions=(region,), now=NOW)

    assert not (tmp_path / "regions/de/post_code/bremen.csv").exists()


def test_refresh_rejects_unconfigured_source_contract(tmp_path: Path) -> None:
    configured = configured_region("bremen")
    custom = GeofabrikRegion(
        configured.name,
        "https://example.test/bremen.osm.pbf",
        primary_state_code=configured.primary_state_code,
        required_state_codes=configured.required_state_codes,
    )

    with pytest.raises(RefreshError, match="configured source contracts"):
        refresh_data(**refresh_paths(tmp_path), regions=(custom,), now=NOW)


def test_scoped_refresh_requires_previous_full_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = configured_region("bremen")
    install_fresh_fakes(monkeypatch)

    with pytest.raises(RefreshError, match="previous full generated_at"):
        refresh_data(**refresh_paths(tmp_path), regions=(region,), now=NOW)

    assert not (tmp_path / "metadata.json").exists()


def test_country_gate_failure_reports_candidate_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = configured_region("bremen")
    paths = refresh_paths(tmp_path)
    seed_full_refresh_timestamp(paths)
    for other in get_country_config("de").geofabrik_regions:
        if other != region:
            write_post_code_csv(
                records_for(other),
                paths["region_output_root"] / "de/post_code" / other.output_name,
            )
    install_fresh_fakes(monkeypatch, scoped_source_only=False)
    report_path = tmp_path / "quality-report.json"

    with pytest.raises(RefreshError, match="minimum is 8000"):
        refresh_data(**paths, regions=(region,), report_path=report_path, now=NOW)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["error_class"] == "quality"
    assert report["countries"][0]["country"] == "de"
    assert report["countries"][0]["records"] > 0
    assert len(report["countries"][0]["state_codes"]) == 16
    assert not (paths["public_output_root"] / "de/post_code.csv").exists()


def test_promotion_rolls_back_all_files_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = configured_region("bremen")
    paths = refresh_paths(tmp_path)
    regional_path = paths["region_output_root"] / "de/post_code/bremen.csv"
    public_csv = paths["public_output_root"] / "de/post_code.csv"
    write_post_code_csv((PostCodeRecord(code="28195", city="Old", state="Bremen"),), regional_path)
    public_csv.parent.mkdir(parents=True, exist_ok=True)
    public_csv.write_text("old-public\n", encoding="utf-8")
    write_metadata(paths["metadata_path"], {}, generated_at="2026-07-01T00:00:00Z")
    before = {
        path: path.read_bytes() for path in (regional_path, public_csv, paths["metadata_path"])
    }
    install_fresh_fakes(monkeypatch)
    original_replace = Path.replace

    def fail_public_csv(source: Path, target: Path) -> Path:
        if source.name == "post_code.csv" and "refresh-transaction-" in str(source):
            raise OSError("injected replacement failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_public_csv)

    with pytest.raises(RefreshError, match="output promotion failed.*injected replacement"):
        refresh_data(**paths, regions=(region,), now=NOW)

    assert {path: path.read_bytes() for path in before} == before
    assert not (paths["public_output_root"] / "de/post_code.json").exists()


def test_refresh_cli_prints_new_status_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_refresh_data(**kwargs: Any) -> RefreshResult:
        kwargs["progress"]("checking")
        return RefreshResult(
            regions=(
                RegionRefreshResult("bremen", "fresh", 1),
                RegionRefreshResult("saarland", "unchanged", 1),
                RegionRefreshResult("sachsen", "reused_last_good", 1),
            ),
            public_records=3,
            countries=(CountryRefreshResult("de", 3),),
        )

    monkeypatch.setattr(refresh_module, "refresh_data", fake_refresh_data)

    assert refresh_module.main(["--download-root", str(tmp_path), "--regions", "bremen"]) == 0
    stdout = capsys.readouterr().out
    assert "checking" in stdout
    assert "1 fresh, 1 unchanged, 1 last-known-good sources" in stdout


def test_refresh_cli_returns_failure_and_writes_json_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refresh_module,
        "refresh_data",
        lambda **_: (_ for _ in ()).throw(RefreshError("failed sources")),
    )
    report_path = tmp_path / "report.json"

    assert (
        refresh_module.main(["--download-root", str(tmp_path), "--report-path", str(report_path)])
        == 1
    )

    assert "Data refresh failed: failed sources" in capsys.readouterr().err
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "failed"


def test_parse_arguments_defaults_metadata_paths_and_accepts_report(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    parsed = parse_arguments(["--download-root", str(tmp_path), "--report-path", str(report)])

    assert parsed.metadata_path == Path("data/sources/geofabrik-regions.json")
    assert parsed.region_output_root == Path("data/regional/v1")
    assert parsed.public_output_root == Path("data/public/v1")
    assert parsed.report_path == report
