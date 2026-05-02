from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import open_postal_codes.refresh_data as refresh_module
from open_postal_codes.countries import GeofabrikRegion, get_country_config
from open_postal_codes.osm_extract import ExtractionError
from open_postal_codes.post_code import PostCodeRecord, write_post_code_csv
from open_postal_codes.refresh_data import (
    CountryRefreshResult,
    RefreshError,
    RefreshResult,
    RegionRefreshResult,
    RemoteMetadata,
    default_regions,
    load_metadata,
    merge_region_outputs,
    parse_arguments,
    parse_countries,
    parse_regions,
    refresh_data,
    write_metadata,
)

pytestmark = pytest.mark.unit


def test_default_regions_use_geofabrik_germany_pbf_urls() -> None:
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
    assert all(region.url.endswith("-latest.osm.pbf") for region in regions)
    assert all(
        region.url.startswith("https://download.geofabrik.de/europe/germany/") for region in regions
    )
    assert all(region.md5_url.endswith(".osm.pbf.md5") for region in regions)


def test_parse_countries_selects_dach_geofabrik_sources() -> None:
    countries = parse_countries("de,at,ch")

    assert countries == (
        get_country_config("DE"),
        get_country_config("AT"),
        get_country_config("CH"),
    )
    assert countries[1].geofabrik_regions[0].url == (
        "https://download.geofabrik.de/europe/austria-latest.osm.pbf"
    )
    assert countries[2].geofabrik_regions[0].url == (
        "https://download.geofabrik.de/europe/switzerland-latest.osm.pbf"
    )


def test_parse_regions_rejects_unknown_names() -> None:
    with pytest.raises(RefreshError, match="unknown"):
        parse_regions("bremen,unknown")


def test_merge_region_outputs_deduplicates_sorted_records(tmp_path: Path) -> None:
    region_root = tmp_path / "regions"
    write_post_code_csv(
        [
            PostCodeRecord(code="28195", city="Bremen"),
            PostCodeRecord(code="66111", city="Saarbruecken"),
        ],
        region_root / "bremen.csv",
    )
    write_post_code_csv(
        [
            PostCodeRecord(code="28195", city="Bremen"),
            PostCodeRecord(code="01067", city="Dresden"),
        ],
        region_root / "sachsen.csv",
    )

    records = merge_region_outputs(region_root)

    assert [record.code for record in records] == ["01067", "28195", "66111"]


def test_metadata_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    metadata = {
        "bremen": RemoteMetadata(
            url="https://example.test/bremen.osm.pbf",
            content_length=3,
            etag="abc",
            last_modified="today",
            md5="900150983cd24fb0d6963f7d28e17f72",
        )
    }

    write_metadata(path, metadata)

    assert load_metadata(path)["bremen"].stable_key() == metadata["bremen"].stable_key()


def test_refresh_data_refreshes_changed_region_and_rebuilds_public_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    metadata = RemoteMetadata(
        url=region.url,
        content_length=3,
        etag="v1",
        last_modified="today",
        md5="900150983cd24fb0d6963f7d28e17f72",
    )

    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", lambda _: metadata)
    monkeypatch.setattr(refresh_module, "download_region", lambda **_: None)

    def fake_extract_region_to_csv(
        input_path: Path,
        output_path: Path,
        *,
        country: str,
    ) -> Any:
        write_post_code_csv([PostCodeRecord(code="28195", city="Bremen")], output_path)
        return type("Extraction", (), {"records": (PostCodeRecord(code="28195", city="Bremen"),)})()

    monkeypatch.setattr(refresh_module, "extract_region_to_csv", fake_extract_region_to_csv)

    result = refresh_data(
        download_root=tmp_path / "downloads",
        metadata_path=tmp_path / "metadata.json",
        region_output_root=tmp_path / "regions",
        public_output_root=tmp_path / "public",
        regions=(region,),
    )

    assert result.public_records == 1
    assert result.regions == (RegionRefreshResult(region="bremen", status="refreshed", records=1),)
    assert (tmp_path / "public/de/post_code.csv").exists()
    assert load_metadata(tmp_path / "metadata.json")["bremen"].etag == "v1"


def test_refresh_data_writes_country_scoped_outputs_for_at_and_ch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    austria = GeofabrikRegion("austria", "https://example.test/austria.osm.pbf", country="at")
    switzerland = GeofabrikRegion(
        "switzerland",
        "https://example.test/switzerland.osm.pbf",
        country="ch",
    )

    def fake_fetch_remote_metadata(region: GeofabrikRegion) -> RemoteMetadata:
        return RemoteMetadata(
            url=region.url,
            content_length=3,
            etag=f"v1-{region.country}",
            last_modified="today",
            md5="900150983cd24fb0d6963f7d28e17f72",
        )

    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", fake_fetch_remote_metadata)
    monkeypatch.setattr(refresh_module, "download_region", lambda **_: None)

    def fake_extract_region_to_csv(input_path: Path, output_path: Path, *, country: str) -> Any:
        record = (
            PostCodeRecord(code="1010", city="Wien", country=country)
            if country == "AT"
            else PostCodeRecord(code="8001", city="Zuerich", country=country)
        )
        write_post_code_csv([record], output_path)
        return type("Extraction", (), {"records": (record,)})()

    monkeypatch.setattr(refresh_module, "extract_region_to_csv", fake_extract_region_to_csv)

    result = refresh_data(
        download_root=tmp_path / "downloads",
        metadata_path=tmp_path / "metadata.json",
        region_output_root=tmp_path / "regions",
        public_output_root=tmp_path / "public",
        regions=(austria, switzerland),
    )

    assert result.public_records == 2
    assert result.countries == (
        CountryRefreshResult(country="at", records=1),
        CountryRefreshResult(country="ch", records=1),
    )
    assert (tmp_path / "regions/at/post_code/austria.csv").exists()
    assert (tmp_path / "regions/ch/post_code/switzerland.csv").exists()
    assert (tmp_path / "public/at/post_code.csv").exists()
    assert (tmp_path / "public/ch/post_code.csv").exists()
    metadata = load_metadata(tmp_path / "metadata.json")
    assert metadata["at/austria"].etag == "v1-at"
    assert metadata["ch/switzerland"].etag == "v1-ch"


def test_refresh_data_skips_unchanged_region_with_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    metadata = RemoteMetadata(
        url=region.url,
        content_length=3,
        etag="v1",
        last_modified="today",
        md5="900150983cd24fb0d6963f7d28e17f72",
    )
    metadata_path = tmp_path / "metadata.json"
    region_root = tmp_path / "regions"
    write_metadata(metadata_path, {"bremen": metadata})
    write_post_code_csv(
        [PostCodeRecord(code="28195", city="Bremen")],
        region_root / "de/post_code/bremen.csv",
    )

    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", lambda _: metadata)

    result = refresh_data(
        download_root=tmp_path / "downloads",
        metadata_path=metadata_path,
        region_output_root=region_root,
        public_output_root=tmp_path / "public",
        regions=(region,),
    )

    assert result.regions == (RegionRefreshResult(region="bremen", status="skipped", records=1),)
    assert (tmp_path / "public/de/post_code.json").exists()


def test_refresh_data_continues_after_unavailable_region_and_fails_at_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unavailable = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    available = GeofabrikRegion("saarland", "https://example.test/saarland.osm.pbf")
    metadata = RemoteMetadata(
        url=available.url,
        content_length=3,
        etag="v1",
        last_modified="today",
        md5="900150983cd24fb0d6963f7d28e17f72",
    )
    downloaded_regions: list[str] = []

    def fake_fetch_remote_metadata(region: GeofabrikRegion) -> RemoteMetadata:
        if region.name == unavailable.name:
            raise RefreshError("required remote file is not available")
        return metadata

    def fake_download_region(**kwargs: Any) -> None:
        downloaded_regions.append(kwargs["region"].name)

    def fake_extract_region_to_csv(
        input_path: Path,
        output_path: Path,
        *,
        country: str,
    ) -> Any:
        write_post_code_csv([PostCodeRecord(code="66111", city="Saarbruecken")], output_path)
        return type(
            "Extraction",
            (),
            {"records": (PostCodeRecord(code="66111", city="Saarbruecken"),)},
        )()

    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", fake_fetch_remote_metadata)
    monkeypatch.setattr(refresh_module, "download_region", fake_download_region)
    monkeypatch.setattr(refresh_module, "extract_region_to_csv", fake_extract_region_to_csv)

    with pytest.raises(RefreshError, match="bremen"):
        refresh_data(
            download_root=tmp_path / "downloads",
            metadata_path=tmp_path / "metadata.json",
            region_output_root=tmp_path / "regions",
            public_output_root=tmp_path / "public",
            regions=(unavailable, available),
        )

    assert downloaded_regions == ["saarland"]
    assert (tmp_path / "public/de/post_code.csv").exists()


def test_refresh_data_collects_extraction_errors_after_other_regions_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    successful = GeofabrikRegion("saarland", "https://example.test/saarland.osm.pbf")
    metadata = RemoteMetadata(
        url=successful.url,
        content_length=3,
        etag="v1",
        last_modified="today",
        md5="900150983cd24fb0d6963f7d28e17f72",
    )

    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", lambda _: metadata)
    monkeypatch.setattr(refresh_module, "download_region", lambda **_: None)

    def fake_extract_region_to_csv(
        input_path: Path,
        output_path: Path,
        *,
        country: str,
    ) -> Any:
        if input_path.name.startswith(failing.name):
            raise ExtractionError("Germany administrative boundary was not found")
        write_post_code_csv([PostCodeRecord(code="66111", city="Saarbruecken")], output_path)
        return type(
            "Extraction",
            (),
            {"records": (PostCodeRecord(code="66111", city="Saarbruecken"),)},
        )()

    monkeypatch.setattr(refresh_module, "extract_region_to_csv", fake_extract_region_to_csv)

    with pytest.raises(RefreshError, match="bremen"):
        refresh_data(
            download_root=tmp_path / "downloads",
            metadata_path=tmp_path / "metadata.json",
            region_output_root=tmp_path / "regions",
            public_output_root=tmp_path / "public",
            regions=(failing, successful),
        )

    assert (tmp_path / "public/de/post_code.json").exists()


def test_refresh_cli_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refresh_module,
        "refresh_data",
        lambda **_: RefreshResult(
            regions=(
                RegionRefreshResult(region="bremen", status="refreshed", records=1),
                RegionRefreshResult(region="saarland", status="skipped", records=1),
            ),
            public_records=2,
            countries=(CountryRefreshResult(country="de", records=2),),
        ),
    )

    assert refresh_module.main(["--download-root", str(tmp_path), "--regions", "bremen"]) == 0

    assert (
        "1 refreshed sources, 1 skipped sources, 1 country outputs, 2 public records"
        in capsys.readouterr().out
    )


def test_refresh_cli_returns_failure_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refresh_module,
        "refresh_data",
        lambda **_: (_ for _ in ()).throw(RefreshError("failed regions")),
    )

    assert refresh_module.main(["--download-root", str(tmp_path)]) == 1

    assert "Data refresh failed: failed regions" in capsys.readouterr().err


def test_parse_arguments_defaults_metadata_paths(tmp_path: Path) -> None:
    parsed = parse_arguments(["--download-root", str(tmp_path)])

    assert parsed.metadata_path == Path("data/sources/geofabrik-regions.json")
    assert parsed.region_output_root == Path("data/regional/v1")
    assert parsed.public_output_root == Path("data/public/v1")


def test_refresh_data_rejects_zero_region_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    metadata = RemoteMetadata(region.url, 3, "", "", "900150983cd24fb0d6963f7d28e17f72")

    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", lambda _: metadata)
    monkeypatch.setattr(refresh_module, "download_region", lambda **_: None)
    monkeypatch.setattr(
        refresh_module,
        "extract_region_to_csv",
        lambda *_args, **_kwargs: type("Extraction", (), {"records": ()})(),
    )

    with pytest.raises(RefreshError, match="zero valid"):
        refresh_data(
            download_root=tmp_path / "downloads",
            metadata_path=tmp_path / "metadata.json",
            region_output_root=tmp_path / "regions",
            public_output_root=tmp_path / "public",
            regions=(region,),
        )


def test_refresh_data_rejects_zero_public_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    metadata = RemoteMetadata(region.url, 3, "", "", "900150983cd24fb0d6963f7d28e17f72")
    metadata_path = tmp_path / "metadata.json"
    write_metadata(metadata_path, {"bremen": metadata})
    (tmp_path / "regions").mkdir()

    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", lambda _: metadata)
    monkeypatch.setattr(refresh_module, "download_region", lambda **_: None)
    monkeypatch.setattr(
        refresh_module,
        "extract_region_to_csv",
        lambda *_args, **_kwargs: type(
            "Extraction",
            (),
            {"records": (PostCodeRecord(code="28195", city="Bremen"),)},
        )(),
    )

    with pytest.raises(RefreshError, match="zero public"):
        refresh_data(
            download_root=tmp_path / "downloads",
            metadata_path=metadata_path,
            region_output_root=tmp_path / "regions",
            public_output_root=tmp_path / "public",
            regions=(region,),
        )


def test_parse_regions_empty_value_uses_default_region_set() -> None:
    assert parse_regions("") is None
