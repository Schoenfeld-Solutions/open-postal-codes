from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

import pytest

import open_postal_codes.refresh_data as refresh_module
from open_postal_codes.countries import GeofabrikRegion
from open_postal_codes.refresh_data import (
    RefreshError,
    RemoteMetadata,
    download_region,
    fetch_remote_md5,
    fetch_remote_metadata,
    remote_headers,
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
