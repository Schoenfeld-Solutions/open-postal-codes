from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import open_postal_codes.refresh_data as refresh_data_module
from open_postal_codes.countries import (
    GeofabrikIntegrityError,
    GeofabrikNetworkError,
    GeofabrikRegion,
    RemoteMetadata,
    get_country_config,
)
from open_postal_codes.osm_extract import ExtractionError
from open_postal_codes.post_code import (
    PostCodeRecord,
    load_metadata,
    write_metadata,
    write_post_code_csv,
)
from open_postal_codes.refresh_data import (
    download_region,
    fetch_remote_md5,
    fetch_remote_metadata,
    refresh_data,
    remote_headers,
    retry_remote,
)

pytestmark = pytest.mark.unit


class FakeResponse(BytesIO):
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(payload)
        self.headers = headers or {}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class FailingReadResponse(FakeResponse):
    """Return one chunk before simulating an interrupted transfer."""

    def __init__(self) -> None:
        super().__init__(b"")
        self.read_count = 0

    def read(self, _size: int | None = -1) -> bytes:
        self.read_count += 1
        if self.read_count == 1:
            return b"partial"
        raise urllib.error.URLError("connection reset")


def http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        "https://example.test/source",
        code,
        "test error",
        headers,
        None,
    )


def no_sleep(monkeypatch: pytest.MonkeyPatch, module: Any) -> None:
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)


def test_fetch_remote_metadata_reads_headers_and_checksum(monkeypatch: pytest.MonkeyPatch) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")

    monkeypatch.setattr(
        refresh_data_module,
        "remote_headers",
        lambda _: {"Content-Length": "3", "ETag": "abc", "Last-Modified": "today"},
    )
    monkeypatch.setattr(
        refresh_data_module,
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


def test_fetch_remote_metadata_rejects_empty_file(monkeypatch: pytest.MonkeyPatch) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    monkeypatch.setattr(refresh_data_module, "remote_headers", lambda _: {"Content-Length": "0"})

    with pytest.raises(GeofabrikIntegrityError, match="empty"):
        fetch_remote_metadata(region)


def test_remote_headers_wraps_unavailable_file(monkeypatch: pytest.MonkeyPatch) -> None:
    no_sleep(monkeypatch, refresh_data_module)

    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(GeofabrikNetworkError, match="not available"):
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

    with pytest.raises(GeofabrikIntegrityError, match="MD5"):
        fetch_remote_md5(region)


def test_fetch_remote_md5_wraps_unavailable_file(monkeypatch: pytest.MonkeyPatch) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    no_sleep(monkeypatch, refresh_data_module)

    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(GeofabrikNetworkError, match="checksum file"):
        fetch_remote_md5(region)


def test_retry_remote_stops_after_three_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("open_postal_codes.refresh_data.time.sleep", sleeps.append)

    with pytest.raises(GeofabrikNetworkError, match="unavailable"):
        retry_remote(operation, "source unavailable")

    assert attempts == 3
    assert sleeps == [2.0, 8.0]


@pytest.mark.parametrize("status", (408, 429, 500, 502, 503, 504))
def test_retry_remote_retries_transient_http_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise http_error(status)
        return "available"

    monkeypatch.setattr("open_postal_codes.refresh_data.time.sleep", sleeps.append)

    assert retry_remote(operation, "source unavailable") == "available"
    assert attempts == 2
    assert sleeps == [2.0]


def test_retry_remote_does_not_retry_http_404(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise http_error(404)

    monkeypatch.setattr("open_postal_codes.refresh_data.time.sleep", sleeps.append)

    with pytest.raises(GeofabrikNetworkError, match="source unavailable"):
        retry_remote(operation, "source unavailable")

    assert attempts == 1
    assert sleeps == []


def test_retry_remote_caps_retry_after_at_sixty_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise http_error(429, retry_after="120")
        return "available"

    monkeypatch.setattr("open_postal_codes.refresh_data.time.sleep", sleeps.append)

    assert retry_remote(operation, "source unavailable") == "available"
    assert sleeps == [60.0]


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
    no_sleep(monkeypatch, refresh_data_module)
    monkeypatch.setattr(refresh_data_module, "fetch_remote_metadata", lambda _: metadata)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(payload),
    )

    with pytest.raises(GeofabrikIntegrityError, match=message):
        download_region(region=region, metadata=metadata, target_path=tmp_path / "bremen.osm.pbf")


def test_download_region_restarts_metadata_and_download_after_checksum_rotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    old_payload = b"old"
    new_payload = b"new"
    old_metadata = RemoteMetadata(
        region.url,
        len(old_payload),
        "old-etag",
        "yesterday",
        hashlib.md5(old_payload, usedforsecurity=False).hexdigest(),
    )
    new_metadata = RemoteMetadata(
        region.url,
        len(new_payload),
        "new-etag",
        "today",
        hashlib.md5(new_payload, usedforsecurity=False).hexdigest(),
    )
    responses = iter((new_payload, new_payload))
    metadata_requests = 0

    def refresh_metadata(_: GeofabrikRegion) -> RemoteMetadata:
        nonlocal metadata_requests
        metadata_requests += 1
        return new_metadata

    no_sleep(monkeypatch, refresh_data_module)
    monkeypatch.setattr(refresh_data_module, "fetch_remote_metadata", refresh_metadata)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(next(responses)),
    )

    target = tmp_path / "bremen.osm.pbf"
    accepted = download_region(region=region, metadata=old_metadata, target_path=target)

    assert accepted == new_metadata
    assert metadata_requests == 1
    assert target.read_bytes() == new_payload
    assert not target.with_suffix(".osm.pbf.part").exists()


def test_download_region_removes_partial_file_after_exhausted_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    metadata = RemoteMetadata(region.url, 8, "", "", "0" * 32)
    attempts = 0

    def interrupted_response(*_args: object, **_kwargs: object) -> FailingReadResponse:
        nonlocal attempts
        attempts += 1
        return FailingReadResponse()

    no_sleep(monkeypatch, refresh_data_module)
    monkeypatch.setattr(urllib.request, "urlopen", interrupted_response)
    target = tmp_path / "bremen.osm.pbf"

    with pytest.raises(GeofabrikNetworkError, match="could not be downloaded"):
        download_region(region=region, metadata=metadata, target_path=target)

    assert attempts == 3
    assert not target.exists()
    assert not target.with_suffix(".osm.pbf.part").exists()


def test_download_region_wraps_download_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    region = GeofabrikRegion("bremen", "https://example.test/bremen.osm.pbf")
    metadata = RemoteMetadata(region.url, 3, "", "", "900150983cd24fb0d6963f7d28e17f72")
    no_sleep(monkeypatch, refresh_data_module)

    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)

    with pytest.raises(GeofabrikNetworkError, match="could not be downloaded"):
        download_region(region=region, metadata=metadata, target_path=tmp_path / "bremen.osm.pbf")


@pytest.mark.parametrize(
    ("failure", "error_class"),
    (("integrity", "integrity"), ("extraction", "extraction"), ("quality", "quality")),
)
def test_known_source_failures_reuse_valid_last_good(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    error_class: str,
) -> None:
    region = next(
        item for item in get_country_config("de").geofabrik_regions if item.name == "bremen"
    )
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    accepted_at = (now - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    record = PostCodeRecord(code="28195", city="Bremen", state="Bremen")
    metadata = RemoteMetadata(
        region.url,
        3,
        "old",
        "yesterday",
        "1" * 32,
        accepted_at=accepted_at,
        verified_at=accepted_at,
        record_count=1,
        unique_post_code_count=1,
        state_codes=("DE-HB",),
    )
    metadata_path = tmp_path / "metadata.json"
    regional_root = tmp_path / "regional"
    regional_path = regional_root / "de/post_code/bremen.csv"
    write_metadata(metadata_path, {region.metadata_key: metadata}, generated_at=accepted_at)
    write_post_code_csv((record,), regional_path)
    before = (metadata_path.read_bytes(), regional_path.read_bytes())
    remote = RemoteMetadata(region.url, 3, "new", "today", "2" * 32)
    monkeypatch.setattr(refresh_data_module, "fetch_remote_metadata", lambda _: remote)
    monkeypatch.setattr(refresh_data_module, "configured_selection", lambda *_: False)
    if failure == "integrity":
        monkeypatch.setattr(
            refresh_data_module,
            "download_region",
            lambda **_: (_ for _ in ()).throw(GeofabrikIntegrityError("mismatch")),
        )
    else:
        monkeypatch.setattr(refresh_data_module, "download_region", lambda **_: remote)
        extraction: object = (
            ExtractionError("broken PBF")
            if failure == "extraction"
            else SimpleNamespace(
                records=(PostCodeRecord(code="28195", city="Bremen", state=""),),
                observed_state_codes=("DE-HB",),
                inferred_state_records=0,
            )
        )
        monkeypatch.setattr(
            refresh_data_module,
            "extract_post_codes_from_osm",
            lambda *_args, **_kwargs: (
                (_ for _ in ()).throw(extraction)
                if isinstance(extraction, BaseException)
                else extraction
            ),
        )

    result = refresh_data(
        download_root=tmp_path / "downloads",
        metadata_path=metadata_path,
        region_output_root=regional_root,
        public_output_root=tmp_path / "public",
        regions=(region,),
        now=now,
    )

    assert result.regions[0].status == "reused_last_good"
    assert result.regions[0].error_class == error_class
    assert (metadata_path.read_bytes(), regional_path.read_bytes()) == before


def test_mixed_fresh_and_last_good_run_updates_only_fresh_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    regions = tuple(
        item
        for item in get_country_config("de").geofabrik_regions
        if item.name in {"bremen", "saarland"}
    )
    states = {"bremen": ("28195", "Bremen"), "saarland": ("66111", "Saarland")}
    now = datetime(2026, 7, 17, 12, tzinfo=UTC)
    timestamp = (now - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    metadata_path, regional_root = tmp_path / "metadata.json", tmp_path / "regional"
    previous: dict[str, RemoteMetadata] = {}
    records: dict[str, tuple[PostCodeRecord, ...]] = {}
    for region in regions:
        code, state = states[region.name]
        records[region.name] = (PostCodeRecord(code=code, city=state, state=state),)
        previous[region.metadata_key] = RemoteMetadata(
            region.url,
            3,
            "old",
            "yesterday",
            "1" * 32,
            accepted_at=timestamp,
            verified_at=timestamp,
            record_count=1,
            unique_post_code_count=1,
            state_codes=region.required_state_codes,
        )
        write_post_code_csv(
            records[region.name], regional_root / f"de/post_code/{region.output_name}"
        )
    write_metadata(metadata_path, previous, generated_at=timestamp)
    fresh = RemoteMetadata(regions[1].url, 3, "new", "today", "2" * 32)
    clock = [0.0]

    def inventory(region: GeofabrikRegion) -> RemoteMetadata:
        if region.name == "bremen":
            raise GeofabrikNetworkError("offline")
        clock[0] += 5.0
        return fresh

    monkeypatch.setattr("open_postal_codes.refresh_data.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(refresh_data_module, "fetch_remote_metadata", inventory)
    monkeypatch.setattr(refresh_data_module, "download_region", lambda **_: fresh)
    monkeypatch.setattr(refresh_data_module, "configured_selection", lambda *_: False)
    monkeypatch.setattr(
        refresh_data_module,
        "extract_post_codes_from_osm",
        lambda *_args, **kwargs: SimpleNamespace(
            records=records[kwargs["region"].name],
            observed_state_codes=kwargs["region"].required_state_codes,
            inferred_state_records=0,
        ),
    )

    result = refresh_data(
        download_root=tmp_path / "downloads",
        metadata_path=metadata_path,
        region_output_root=regional_root,
        public_output_root=tmp_path / "public",
        regions=regions,
        now=now,
    )
    updated = load_metadata(metadata_path)

    assert [item.status for item in result.regions] == ["reused_last_good", "fresh"]
    assert result.regions[1].duration_seconds == 5.0
    assert updated[regions[0].metadata_key] == previous[regions[0].metadata_key]
    assert updated[regions[1].metadata_key].md5 == fresh.md5


def test_inventory_abort_reports_every_selected_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    regions = tuple(
        region
        for region in get_country_config("de").geofabrik_regions
        if region.name in {"bremen", "saarland"}
    )
    report_path = tmp_path / "report.json"
    metadata_path = tmp_path / "metadata.json"
    write_metadata(metadata_path, {}, generated_at="2026-07-17T12:00:00Z")

    def inventory(region: GeofabrikRegion) -> RemoteMetadata:
        if region.name == "saarland":
            raise GeofabrikNetworkError("offline")
        return RemoteMetadata(region.url, 3, "etag", "today", "2" * 32)

    monkeypatch.setattr(refresh_data_module, "fetch_remote_metadata", inventory)

    with pytest.raises(refresh_data_module.RefreshError, match="offline"):
        refresh_data(
            download_root=tmp_path / "downloads",
            metadata_path=metadata_path,
            region_output_root=tmp_path / "regional",
            public_output_root=tmp_path / "public",
            regions=regions,
            report_path=report_path,
            now=datetime(2026, 7, 17, 12, tzinfo=UTC),
        )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    sources = report["sources"]
    assert [(source["region"], source["status"]) for source in sources] == [
        ("bremen", "failed"),
        ("saarland", "failed"),
    ]
    assert sources[0]["error_class"] == "refresh"
    assert sources[0]["md5"] == "2" * 32
    assert sources[1]["error_class"] == "network"
