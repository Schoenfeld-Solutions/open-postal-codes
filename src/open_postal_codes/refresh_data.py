"""Refresh public D-A-CH post code files from Geofabrik PBFs."""

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

from open_postal_codes.countries import (
    COUNTRY_CONFIGS,
    CountryConfig,
    GeofabrikRegion,
    default_geofabrik_regions,
    get_country_config,
)
from open_postal_codes.osm_extract import ExtractionError, extract_region_to_csv
from open_postal_codes.post_code import (
    PostCodeRecord,
    dedupe_records,
    read_post_code_csv,
    write_public_post_code_files,
)

MD5_PATTERN = re.compile(r"\b(?P<md5>[0-9a-fA-F]{32})\b")


class RefreshError(RuntimeError):
    """Raised when a data refresh cannot safely complete."""


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
    country: str = "de"


@dataclass(frozen=True)
class CountryRefreshResult:
    """Summary for one public country output."""

    country: str
    records: int


@dataclass(frozen=True)
class RefreshResult:
    """Summary for a completed refresh."""

    regions: tuple[RegionRefreshResult, ...]
    public_records: int
    countries: tuple[CountryRefreshResult, ...] = ()


def default_regions() -> tuple[GeofabrikRegion, ...]:
    """Return the Germany regional source set used by scoped smoke runs."""

    return get_country_config("de").geofabrik_regions


def selected_regions_for_countries(
    countries: tuple[CountryConfig, ...] | None,
) -> tuple[GeofabrikRegion, ...]:
    """Return source files for selected countries or all D-A-CH countries."""

    return default_geofabrik_regions(countries)


def refresh_data(
    *,
    download_root: Path,
    metadata_path: Path,
    region_output_root: Path,
    public_output_root: Path,
    regions: tuple[GeofabrikRegion, ...] | None = None,
    countries: tuple[CountryConfig, ...] | None = None,
) -> RefreshResult:
    """Refresh changed source outputs and rebuild public post code files."""

    if regions is not None and countries is not None:
        country_slugs = {country.slug for country in countries}
        if country_slugs != {"de"}:
            raise RefreshError("--regions can only be combined with --countries de")

    selected_regions = regions or selected_regions_for_countries(countries)
    selected_countries = countries_for_regions(selected_regions)
    previous_metadata = load_metadata(metadata_path)
    region_results: list[RegionRefreshResult] = []
    country_results: list[CountryRefreshResult] = []
    new_metadata: dict[str, RemoteMetadata] = dict(previous_metadata)
    failures: list[str] = []

    download_root.mkdir(parents=True, exist_ok=True)
    for country in selected_countries:
        country_region_output_root(region_output_root, country).mkdir(parents=True, exist_ok=True)

    for region in selected_regions:
        country_config = get_country_config(region.country)
        try:
            metadata = fetch_remote_metadata(region)
            new_metadata[region.metadata_key] = metadata
            output_path = region_output_path(region_output_root, region)
            previous_region_metadata = previous_metadata.get(region.metadata_key)

            if (
                output_path.exists()
                and previous_region_metadata is not None
                and previous_region_metadata.stable_key() == metadata.stable_key()
            ):
                record_count = len(read_post_code_csv(output_path))
                region_results.append(
                    RegionRefreshResult(
                        region=region.name,
                        status="skipped",
                        records=record_count,
                        country=country_config.slug,
                    )
                )
                continue

            pbf_path = download_root / country_config.slug / f"{region.name}.osm.pbf"
            download_region(region=region, metadata=metadata, target_path=pbf_path)
            extraction = extract_region_to_csv(
                pbf_path,
                output_path,
                country=country_config.code,
            )
            if not extraction.records:
                raise RefreshError(f"{region.name} produced zero valid post code records")
            region_results.append(
                RegionRefreshResult(
                    region=region.name,
                    status="refreshed",
                    records=len(extraction.records),
                    country=country_config.slug,
                )
            )
        except (ExtractionError, RefreshError) as error:
            failures.append(f"{country_config.slug}/{region.name}: {error}")
            region_results.append(
                RegionRefreshResult(
                    region=region.name,
                    status="failed",
                    records=0,
                    country=country_config.slug,
                )
            )

    public_count = 0
    for country in selected_countries:
        all_records = merge_region_outputs(country_region_output_root(region_output_root, country))
        if not all_records:
            if failures:
                joined_failures = "\n".join(failures)
                raise RefreshError(
                    f"{country.slug} regional outputs produced zero public post code records "
                    "after failed sources:\n"
                    f"{joined_failures}"
                )
            raise RefreshError(
                f"{country.slug} regional outputs produced zero public post code records"
            )
        country_count = write_public_post_code_files(
            all_records,
            public_country_output_root(public_output_root, country),
        )
        country_results.append(CountryRefreshResult(country=country.slug, records=country_count))
        public_count += country_count

    if failures:
        joined_failures = "\n".join(failures)
        raise RefreshError(f"data refresh completed with failed sources:\n{joined_failures}")

    write_metadata(metadata_path, new_metadata)

    return RefreshResult(
        regions=tuple(region_results),
        public_records=public_count,
        countries=tuple(country_results),
    )


def countries_for_regions(regions: tuple[GeofabrikRegion, ...]) -> tuple[CountryConfig, ...]:
    """Return country configs represented by selected source files."""

    countries_by_slug = {country.slug: country for country in COUNTRY_CONFIGS}
    selected_slugs = {get_country_config(region.country).slug for region in regions}
    return tuple(country for slug, country in countries_by_slug.items() if slug in selected_slugs)


def country_region_output_root(root: Path, country: CountryConfig) -> Path:
    """Return the normalized regional CSV output root for one country."""

    return root / country.slug / "post_code"


def region_output_path(root: Path, region: GeofabrikRegion) -> Path:
    """Return the normalized CSV output path for one source file."""

    country_config = get_country_config(region.country)
    return country_region_output_root(root, country_config) / region.output_name


def public_country_output_root(root: Path, country: CountryConfig) -> Path:
    """Return the public API source root for one country."""

    return root / country.slug


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
    target_path.parent.mkdir(parents=True, exist_ok=True)

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
        "source": "Geofabrik D-A-CH PBF files",
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
    default_region_names = {region.name for region in default_regions()}
    unknown = requested.difference(default_region_names)
    if unknown:
        raise RefreshError(f"unknown Geofabrik region names: {', '.join(sorted(unknown))}")
    return tuple(region for region in default_regions() if region.name in requested)


def parse_countries(value: str | None) -> tuple[CountryConfig, ...] | None:
    if not value:
        return None
    requested = tuple(country.strip() for country in value.split(",") if country.strip())
    try:
        return tuple(get_country_config(country) for country in requested)
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
    parser.add_argument(
        "--region-output-root",
        type=Path,
        default=Path("data/regional/v1"),
    )
    parser.add_argument(
        "--public-output-root",
        type=Path,
        default=Path("data/public/v1"),
    )
    parser.add_argument(
        "--countries",
        help="Optional comma-separated country slugs or ISO codes. Defaults to de,at,ch.",
    )
    parser.add_argument(
        "--regions",
        help="Optional comma-separated Germany Geofabrik region names for manual smoke runs.",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = parse_arguments(arguments)
    regions = parse_regions(parsed_arguments.regions)
    countries = parse_countries(parsed_arguments.countries)
    if regions is not None and countries is None:
        countries = (get_country_config("de"),)
    try:
        result = refresh_data(
            download_root=parsed_arguments.download_root,
            metadata_path=parsed_arguments.metadata_path,
            region_output_root=parsed_arguments.region_output_root,
            public_output_root=parsed_arguments.public_output_root,
            regions=regions,
            countries=countries,
        )
    except RefreshError as error:
        print(f"Data refresh failed: {error}", file=sys.stderr)
        return 1

    refreshed = sum(1 for region in result.regions if region.status == "refreshed")
    skipped = sum(1 for region in result.regions if region.status == "skipped")
    print(
        "Data refresh completed: "
        f"{refreshed} refreshed sources, "
        f"{skipped} skipped sources, "
        f"{len(result.countries)} country outputs, "
        f"{result.public_records} public records."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
