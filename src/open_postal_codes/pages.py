"""Package the static GitHub Pages site and file API."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_postal_codes.countries import COUNTRY_CONFIGS

API_VERSION = "v1"
PAGES_BASE_PATH = "/open-postal-codes/"
API_BASE_PATH = f"{PAGES_BASE_PATH}api/{API_VERSION}/"

DATA_FORMATS: tuple[tuple[str, str, str], ...] = (
    ("csv", "CSV", "text/csv; charset=utf-8"),
    ("json", "JSON", "application/json; charset=utf-8"),
    ("xml", "XML", "application/xml; charset=utf-8"),
)

DATA_FILES: tuple[tuple[str, str, str, str], ...] = tuple(
    (
        f"{country.slug}-post-code-{extension}",
        f"{country.slug}/post_code.{extension}",
        f"{country.adjective} post code records as {label}.",
        media_type,
    )
    for country in COUNTRY_CONFIGS
    for extension, label, media_type in DATA_FORMATS
)


@dataclass(frozen=True)
class PackagedFile:
    """Metadata for one published API file."""

    identifier: str
    path: str
    description: str
    media_type: str
    byte_count: int
    gzip_byte_count: int
    line_count: int
    record_count: int
    sha256: str
    gzip_sha256: str

    def to_manifest_entry(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "path": self.path,
            "url": f"{API_BASE_PATH}{self.path}",
            "gzip_url": f"{API_BASE_PATH}{self.path}.gz",
            "description": self.description,
            "media_type": self.media_type,
            "bytes": self.byte_count,
            "gzip_bytes": self.gzip_byte_count,
            "lines": self.line_count,
            "records": self.record_count,
            "sha256": self.sha256,
            "gzip_sha256": self.gzip_sha256,
        }


@dataclass(frozen=True)
class PackageResult:
    """Summary for a completed Pages packaging run."""

    output_root: Path
    manifest_path: Path
    files: tuple[PackagedFile, ...]


def package_pages_site(
    *,
    repository_root: Path,
    output_root: Path,
    generated_at: datetime | None = None,
) -> PackageResult:
    """Create a GitHub Pages artifact tree from the repository sources."""

    site_root = repository_root / "site"
    data_root = repository_root / "data" / "public" / API_VERSION

    if generated_at is None:
        generated_at = datetime.now(UTC)

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    copy_static_site(site_root=site_root, output_root=output_root)

    api_root = output_root / "api" / API_VERSION
    api_root.mkdir(parents=True, exist_ok=True)

    packaged_files: list[PackagedFile] = []
    for identifier, relative_path, description, media_type in DATA_FILES:
        source_path = data_root / relative_path
        target_path = api_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        gzip_path = gzip_file(target_path)
        packaged_files.append(
            PackagedFile(
                identifier=identifier,
                path=relative_path,
                description=description,
                media_type=media_type,
                byte_count=target_path.stat().st_size,
                gzip_byte_count=gzip_path.stat().st_size,
                line_count=count_lines(target_path),
                record_count=count_records(target_path),
                sha256=sha256_file(target_path),
                gzip_sha256=sha256_file(gzip_path),
            )
        )

    manifest = build_manifest(
        generated_at=generated_at,
        data_refreshed_at=read_data_refreshed_at(repository_root),
        files=tuple(packaged_files),
    )
    manifest_path = api_root / "index.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return PackageResult(
        output_root=output_root,
        manifest_path=manifest_path,
        files=tuple(packaged_files),
    )


def copy_static_site(*, site_root: Path, output_root: Path) -> None:
    for source_path in site_root.rglob("*"):
        if not source_path.is_file():
            continue
        target_path = output_root / source_path.relative_to(site_root)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)


def build_manifest(
    *,
    generated_at: datetime,
    data_refreshed_at: str | None = None,
    files: tuple[PackagedFile, ...],
) -> dict[str, Any]:
    return {
        "name": "Open Postal Codes",
        "version": API_VERSION,
        "generated_at": generated_at.astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "data_refreshed_at": data_refreshed_at,
        "base_path": API_BASE_PATH,
        "license": "ODbL-1.0",
        "attribution": [
            "OpenStreetMap contributors",
            "Geofabrik GmbH",
            "OpenPLZ API Data by Frank Stueber",
            "Schoenfeld Solutions",
        ],
        "files": [packaged_file.to_manifest_entry() for packaged_file in files],
    }


def read_data_refreshed_at(repository_root: Path) -> str | None:
    metadata_path = repository_root / "data" / "sources" / "geofabrik-regions.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        return None
    return generated_at


def gzip_file(path: Path) -> Path:
    gzip_path = path.with_name(f"{path.name}.gz")
    with (
        path.open("rb") as source_stream,
        gzip.open(gzip_path, "wb", compresslevel=9) as gzip_stream,
    ):
        shutil.copyfileobj(source_stream, gzip_stream)
    return gzip_path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_lines(path: Path) -> int:
    line_count = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            line_count += chunk.count(b"\n")
    return line_count


def count_records(path: Path) -> int:
    if path.suffix == ".csv":
        return max(count_lines(path) - 1, 0)
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records", [])
        if not isinstance(records, list):
            return 0
        return len(records)
    if path.suffix == ".xml":
        root = ElementTree.parse(path).getroot()
        return len(root.findall("record"))
    return 0


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing site/ and data/public/v1/.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("out"),
        help="Output directory for the GitHub Pages artifact.",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = parse_arguments(arguments)
    result = package_pages_site(
        repository_root=parsed_arguments.repository_root,
        output_root=parsed_arguments.output_root,
    )
    print(f"Packaged {len(result.files)} API files into {result.output_root}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
