from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

import open_postal_codes.refresh_data as refresh_module
from open_postal_codes.osm_extract import ExtractionError
from open_postal_codes.post_code import PostCodeRecord, write_post_code_csv
from open_postal_codes.refresh_data import (
    GeofabrikRegion,
    RefreshError,
    RefreshResult,
    RegionRefreshResult,
    RemoteMetadata,
    default_regions,
    download_region,
    fetch_remote_md5,
    fetch_remote_metadata,
    load_metadata,
    merge_region_outputs,
    parse_arguments,
    parse_regions,
    refresh_data,
    remote_headers,
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

    def fake_extract_region_to_csv(input_path: Path, output_path: Path) -> Any:
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
    assert (tmp_path / "public/post_code.csv").exists()
    assert load_metadata(tmp_path / "metadata.json")["bremen"].etag == "v1"


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
    write_post_code_csv([PostCodeRecord(code="28195", city="Bremen")], region_root / "bremen.csv")

    monkeypatch.setattr(refresh_module, "fetch_remote_metadata", lambda _: metadata)

    result = refresh_data(
        download_root=tmp_path / "downloads",
        metadata_path=metadata_path,
        region_output_root=region_root,
        public_output_root=tmp_path / "public",
        regions=(region,),
    )

    assert result.regions == (RegionRefreshResult(region="bremen", status="skipped", records=1),)
    assert (tmp_path / "public/post_code.json").exists()


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

    def fake_extract_region_to_csv(input_path: Path, output_path: Path) -> Any:
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
    assert (tmp_path / "public/post_code.csv").exists()


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

    def fake_extract_region_to_csv(input_path: Path, output_path: Path) -> Any:
        if input_path.name.startswith(failing.name):
            raise ExtractionError("German administrative boundary was not found")
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

    assert (tmp_path / "public/post_code.json").exists()


class FakeResponse(BytesIO):
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(payload)
        self.headers = headers or {}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def test_fetch_remote_metadata_reads_headers_and_checksum(monkeypatch: pytest.MonkeyPatch) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")

    monkeypatch.setattr(
        refresh_module,
        "remote_headers",
        lambda _: {"Content-Length": "3", "ETag": "abc", "Last-Modified": "today"},
    )
    monkeypatch.setattr(
        refresh_module,
        "fetch_remote_md5",
        lambda _: "900150983cd24fb0d6963f7d28e17f72",
    )

    metadata = fetch_remote_metadata(region)

    assert metadata.content_length == 3
    assert metadata.etag == "abc"
    assert metadata.md5 == "900150983cd24fb0d6963f7d28e17f72"


def test_download_region_validates_size_and_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    payload = b"abc"
    metadata = RemoteMetadata(
        url=region.url,
        content_length=len(payload),
        etag="",
        last_modified="",
        md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
    )
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    target_path = tmp_path / "bremen.osm.pbf"
    download_region(region=region, metadata=metadata, target_path=target_path)

    assert target_path.read_bytes() == payload


def test_download_region_reuses_existing_valid_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    payload = b"abc"
    metadata = RemoteMetadata(
        url=region.url,
        content_length=len(payload),
        etag="",
        last_modified="",
        md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
    )
    target_path = tmp_path / "bremen.osm.pbf"
    target_path.write_bytes(payload)

    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("existing file should be reused")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    download_region(region=region, metadata=metadata, target_path=target_path)

    assert target_path.read_bytes() == payload


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
        ),
    )

    assert refresh_module.main(["--download-root", str(tmp_path), "--regions", "bremen"]) == 0

    assert "1 refreshed regions, 1 skipped regions, 2 public records" in capsys.readouterr().out


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


def test_fetch_remote_metadata_rejects_empty_file(monkeypatch: pytest.MonkeyPatch) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    monkeypatch.setattr(refresh_module, "remote_headers", lambda _: {"Content-Length": "0"})

    with pytest.raises(RefreshError, match="empty"):
        fetch_remote_metadata(region)


def test_remote_headers_wraps_unavailable_file(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(RefreshError, match="not available"):
        remote_headers("https://example.test/missing.osm.pbf")


def test_fetch_remote_md5_parses_checksum(monkeypatch: pytest.MonkeyPatch) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"900150983cd24fb0d6963f7d28e17f72  file\n"),
    )

    assert fetch_remote_md5(region) == "900150983cd24fb0d6963f7d28e17f72"


def test_fetch_remote_md5_rejects_invalid_checksum(monkeypatch: pytest.MonkeyPatch) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"not-a-checksum\n"),
    )

    with pytest.raises(RefreshError, match="MD5"):
        fetch_remote_md5(region)


def test_fetch_remote_md5_wraps_unavailable_file(monkeypatch: pytest.MonkeyPatch) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")

    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(RefreshError, match="checksum file"):
        fetch_remote_md5(region)


@pytest.mark.parametrize(
    ("payload", "content_length", "md5", "message"),
    [
        (b"", 0, "d41d8cd98f00b204e9800998ecf8427e", "empty"),
        (b"abc", 4, "900150983cd24fb0d6963f7d28e17f72", "size mismatch"),
        (b"abc", 3, "00000000000000000000000000000000", "checksum mismatch"),
    ],
)
def test_download_region_rejects_invalid_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    content_length: int,
    md5: str,
    message: str,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    metadata = RemoteMetadata(region.url, content_length, "", "", md5)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(payload),
    )

    with pytest.raises(RefreshError, match=message):
        download_region(region=region, metadata=metadata, target_path=tmp_path / "bremen.osm.pbf")


def test_download_region_wraps_download_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    metadata = RemoteMetadata(region.url, 3, "", "", "900150983cd24fb0d6963f7d28e17f72")

    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(RefreshError, match="could not be downloaded"):
        download_region(region=region, metadata=metadata, target_path=tmp_path / "bremen.osm.pbf")


def test_parse_regions_empty_value_uses_default_region_set() -> None:
    assert parse_regions("") is None
