"""Refresh public German post code files from Geofabrik regional PBFs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_postal_codes.osm_extract import ExtractionError, extract_region_to_csv
from open_postal_codes.post_code import (
    PostCodeRecord,
    dedupe_records,
    read_post_code_csv,
    write_public_post_code_files,
)

GEOFABRIK_GERMANY_BASE_URL = "https://download.geofabrik.de/europe/germany"
REGIONAL_SOURCE_NAMES = (
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
MD5_PATTERN = re.compile(r"\b(?P<md5>[0-9a-fA-F]{32})\b")


class RefreshError(RuntimeError):
    """Raised when a data refresh cannot safely complete."""


@dataclass(frozen=True)
class GeofabrikRegion:
    """One Geofabrik regional Germany source."""

    name: str
    url: str

    @property
    def md5_url(self) -> str:
        return f"{self.url}.md5"

    @property
    def output_name(self) -> str:
        return f"{self.name}.csv"


@dataclass(frozen=True)
class RemoteMetadata:
    """Remote file metadata used to skip unchanged regions."""

    url: str
    content_length: int | None
    etag: str
    last_modified: str
    md5: str

    def stable_key(self) -> tuple[str, int | None, str, str, str]:
        return (self.url, self.content_length, self.etag, self.last_modified, self.md5)


@dataclass(frozen=True)
class RegionRefreshResult:
    """Summary for one regional refresh."""

    region: str
    status: str
    records: int


@dataclass(frozen=True)
class RefreshResult:
    """Summary for a completed refresh."""

    regions: tuple[RegionRefreshResult, ...]
    public_records: int


def default_regions() -> tuple[GeofabrikRegion, ...]:
    return tuple(
        GeofabrikRegion(
            name=name,
            url=f"{GEOFABRIK_GERMANY_BASE_URL}/{name}-latest.osm.pbf",
        )
        for name in REGIONAL_SOURCE_NAMES
    )


def refresh_data(
    *,
    download_root: Path,
    metadata_path: Path,
    region_output_root: Path,
    public_output_root: Path,
    regions: tuple[GeofabrikRegion, ...] | None = None,
) -> RefreshResult:
    """Refresh changed regional outputs and rebuild public post code files."""

    selected_regions = regions or default_regions()
    previous_metadata = load_metadata(metadata_path)
    region_results: list[RegionRefreshResult] = []
    new_metadata: dict[str, RemoteMetadata] = dict(previous_metadata)
    failures: list[str] = []

    download_root.mkdir(parents=True, exist_ok=True)
    region_output_root.mkdir(parents=True, exist_ok=True)

    for region in selected_regions:
        try:
            metadata = fetch_remote_metadata(region)
            new_metadata[region.name] = metadata
            output_path = region_output_root / region.output_name
            previous_region_metadata = previous_metadata.get(region.name)

            if (
                output_path.exists()
                and previous_region_metadata is not None
                and previous_region_metadata.stable_key() == metadata.stable_key()
            ):
                record_count = len(read_post_code_csv(output_path))
                region_results.append(
                    RegionRefreshResult(region=region.name, status="skipped", records=record_count)
                )
                continue

            pbf_path = download_root / f"{region.name}.osm.pbf"
            download_region(region=region, metadata=metadata, target_path=pbf_path)
            extraction = extract_region_to_csv(pbf_path, output_path)
            if not extraction.records:
                raise RefreshError(f"{region.name} produced zero valid post code records")
            region_results.append(
                RegionRefreshResult(
                    region=region.name,
                    status="refreshed",
                    records=len(extraction.records),
                )
            )
        except (ExtractionError, RefreshError) as error:
            failures.append(f"{region.name}: {error}")
            region_results.append(
                RegionRefreshResult(region=region.name, status="failed", records=0)
            )

    all_records = merge_region_outputs(region_output_root)
    if not all_records:
        if failures:
            joined_failures = "\n".join(failures)
            raise RefreshError(
                "regional outputs produced zero public post code records after failed regions:\n"
                f"{joined_failures}"
            )
        raise RefreshError("regional outputs produced zero public post code records")

    public_count = write_public_post_code_files(all_records, public_output_root)

    if failures:
        joined_failures = "\n".join(failures)
        raise RefreshError(f"data refresh completed with failed regions:\n{joined_failures}")

    write_metadata(metadata_path, new_metadata)

    return RefreshResult(regions=tuple(region_results), public_records=public_count)


def fetch_remote_metadata(region: GeofabrikRegion) -> RemoteMetadata:
    headers = remote_headers(region.url)
    content_length_header = headers.get("Content-Length")
    content_length = int(content_length_header) if content_length_header else None
    if content_length is not None and content_length <= 0:
        raise RefreshError(f"{region.url} is empty")
    return RemoteMetadata(
        url=region.url,
        content_length=content_length,
        etag=headers.get("ETag", ""),
        last_modified=headers.get("Last-Modified", ""),
        md5=fetch_remote_md5(region),
    )


def remote_headers(url: str) -> dict[str, str]:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return dict(response.headers.items())
    except urllib.error.URLError as error:
        raise RefreshError(f"required remote file is not available: {url}") from error


def fetch_remote_md5(region: GeofabrikRegion) -> str:
    try:
        with urllib.request.urlopen(region.md5_url, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as error:
        raise RefreshError(f"required checksum file is not available: {region.md5_url}") from error

    match = MD5_PATTERN.search(text)
    if match is None:
        raise RefreshError(f"checksum file does not contain an MD5 digest: {region.md5_url}")
    return match.group("md5").lower()


def download_region(
    *,
    region: GeofabrikRegion,
    metadata: RemoteMetadata,
    target_path: Path,
) -> None:
    if _existing_download_matches(target_path, metadata):
        return

    temporary_path = target_path.with_suffix(f"{target_path.suffix}.part")
    digest = hashlib.md5(usedforsecurity=False)
    byte_count = 0

    try:
        with (
            urllib.request.urlopen(region.url, timeout=120) as response,
            temporary_path.open("wb") as output_stream,
        ):
            while chunk := response.read(1024 * 1024):
                output_stream.write(chunk)
                digest.update(chunk)
                byte_count += len(chunk)
    except urllib.error.URLError as error:
        temporary_path.unlink(missing_ok=True)
        raise RefreshError(f"required remote file could not be downloaded: {region.url}") from error

    if byte_count <= 0:
        temporary_path.unlink(missing_ok=True)
        raise RefreshError(f"{region.url} downloaded as an empty file")
    if metadata.content_length is not None and byte_count != metadata.content_length:
        temporary_path.unlink(missing_ok=True)
        raise RefreshError(
            f"{region.url} size mismatch: expected {metadata.content_length}, got {byte_count}"
        )
    if digest.hexdigest() != metadata.md5:
        temporary_path.unlink(missing_ok=True)
        raise RefreshError(f"{region.url} checksum mismatch")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(temporary_path), target_path)


def _existing_download_matches(path: Path, metadata: RemoteMetadata) -> bool:
    if not path.exists():
        return False
    byte_count = path.stat().st_size
    if byte_count <= 0:
        return False
    if metadata.content_length is not None and byte_count != metadata.content_length:
        return False

    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as input_stream:
        while chunk := input_stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest() == metadata.md5


def merge_region_outputs(region_output_root: Path) -> tuple[PostCodeRecord, ...]:
    records: list[PostCodeRecord] = []
    for path in sorted(region_output_root.glob("*.csv")):
        records.extend(read_post_code_csv(path))
    return dedupe_records(records)


def load_metadata(path: Path) -> dict[str, RemoteMetadata]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    regions = payload.get("regions", {})
    return {
        name: RemoteMetadata(
            url=values["url"],
            content_length=values.get("content_length"),
            etag=values.get("etag", ""),
            last_modified=values.get("last_modified", ""),
            md5=values.get("md5", ""),
        )
        for name, values in regions.items()
    }


def write_metadata(path: Path, metadata: dict[str, RemoteMetadata]) -> None:
    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "Geofabrik regional Germany PBF files",
        "regions": {
            region: asdict(region_metadata)
            for region, region_metadata in sorted(metadata.items(), key=lambda item: item[0])
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_regions(value: str | None) -> tuple[GeofabrikRegion, ...] | None:
    if not value:
        return None
    requested = {name.strip() for name in value.split(",") if name.strip()}
    unknown = requested.difference(REGIONAL_SOURCE_NAMES)
    if unknown:
        raise RefreshError(f"unknown Geofabrik region names: {', '.join(sorted(unknown))}")
    return tuple(region for region in default_regions() if region.name in requested)


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument(
        "--metadata-path",
        type=Path,
        default=Path("data/sources/geofabrik-regions.json"),
    )
    parser.add_argument(
        "--region-output-root",
        type=Path,
        default=Path("data/regional/v1/de/post_code"),
    )
    parser.add_argument(
        "--public-output-root",
        type=Path,
        default=Path("data/public/v1/de"),
    )
    parser.add_argument(
        "--regions",
        help="Optional comma-separated Geofabrik region names for manual smoke runs.",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = parse_arguments(arguments)
    regions = parse_regions(parsed_arguments.regions)
    try:
        result = refresh_data(
            download_root=parsed_arguments.download_root,
            metadata_path=parsed_arguments.metadata_path,
            region_output_root=parsed_arguments.region_output_root,
            public_output_root=parsed_arguments.public_output_root,
            regions=regions,
        )
    except RefreshError as error:
        print(f"Data refresh failed: {error}", file=sys.stderr)
        return 1

    refreshed = sum(1 for region in result.regions if region.status == "refreshed")
    skipped = sum(1 for region in result.regions if region.status == "skipped")
    print(
        "Data refresh completed: "
        f"{refreshed} refreshed regions, "
        f"{skipped} skipped regions, "
        f"{result.public_records} public records."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
