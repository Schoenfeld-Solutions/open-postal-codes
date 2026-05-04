"""Check the generated GitHub Pages artifact."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from open_postal_codes.pages import (
    API_BASE_PATH,
    API_VERSION,
    DATA_FILES,
    count_lines,
    count_records,
    package_pages_site,
    sha256_file,
)
from tools.repo_checks.common import fail

STATIC_SITE_FILES = (
    "index.html",
    "404.html",
    "favicon.ico",
    "assets/site.css",
    "assets/site.js",
)


def expected_files() -> dict[str, tuple[str, str, str]]:
    return {
        relative_path: (identifier, description, media_type)
        for identifier, relative_path, description, media_type in DATA_FILES
    }


def validate_pages_artifact(repository_root: Path = Path(".")) -> list[str]:
    with TemporaryDirectory(prefix="open-postal-codes-pages-") as temporary_root:
        output_root = Path(temporary_root) / "out"
        try:
            package_pages_site(
                repository_root=repository_root,
                output_root=output_root,
                generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        except Exception as error:  # pragma: no cover - exercised through callers on failures.
            return [f"Pages packaging failed: {error}"]
        return validate_packaged_output(output_root)


def validate_packaged_output(output_root: Path) -> list[str]:
    errors: list[str] = []
    api_root = output_root / "api" / API_VERSION

    for file_name in STATIC_SITE_FILES:
        path = output_root / file_name
        if not path.is_file():
            errors.append(f"missing static Pages file: {path}")

    manifest_path = api_root / "index.json"
    if not manifest_path.is_file():
        return [*errors, f"missing Pages manifest: {manifest_path}"]

    try:
        manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        return [*errors, f"invalid Pages manifest JSON: {error}"]

    if manifest.get("version") != API_VERSION:
        errors.append(f"manifest version must be {API_VERSION}")
    if manifest.get("base_path") != API_BASE_PATH:
        errors.append(f"manifest base_path must be {API_BASE_PATH}")
    data_refreshed_at = manifest.get("data_refreshed_at")
    if data_refreshed_at is not None and not isinstance(data_refreshed_at, str):
        errors.append("manifest data_refreshed_at must be a string or null")

    files = manifest.get("files")
    if not isinstance(files, list):
        return [*errors, "manifest files must be a list"]

    expected = expected_files()
    entries_by_path: dict[str, dict[str, Any]] = {}
    for entry in files:
        if not isinstance(entry, dict):
            errors.append("manifest files contains a non-object entry")
            continue
        relative_path = entry.get("path")
        if not isinstance(relative_path, str):
            errors.append("manifest file entry is missing a string path")
            continue
        if relative_path in entries_by_path:
            errors.append(f"manifest has duplicate file entry: {relative_path}")
        entries_by_path[relative_path] = entry

    if len(files) != len(expected):
        errors.append(f"manifest lists {len(files)} files; expected {len(expected)}")

    missing_paths = sorted(set(expected).difference(entries_by_path))
    extra_paths = sorted(set(entries_by_path).difference(expected))
    if missing_paths:
        errors.append(f"manifest is missing files: {', '.join(missing_paths)}")
    if extra_paths:
        errors.append(f"manifest includes unexpected files: {', '.join(extra_paths)}")

    for relative_path, (identifier, description, media_type) in expected.items():
        entry = entries_by_path.get(relative_path)
        if entry is None:
            continue
        errors.extend(
            validate_manifest_entry(
                entry=entry,
                api_root=api_root,
                relative_path=relative_path,
                identifier=identifier,
                description=description,
                media_type=media_type,
            )
        )

    return errors


def validate_manifest_entry(
    *,
    entry: dict[str, Any],
    api_root: Path,
    relative_path: str,
    identifier: str,
    description: str,
    media_type: str,
) -> list[str]:
    errors: list[str] = []
    data_path = api_root / relative_path
    gzip_path = data_path.with_name(f"{data_path.name}.gz")

    expected_values: dict[str, Any] = {
        "id": identifier,
        "description": description,
        "media_type": media_type,
        "url": f"{API_BASE_PATH}{relative_path}",
        "gzip_url": f"{API_BASE_PATH}{relative_path}.gz",
    }
    for key, expected_value in expected_values.items():
        if entry.get(key) != expected_value:
            errors.append(f"manifest entry for {relative_path} has unexpected {key}")

    if not data_path.is_file():
        return [*errors, f"missing packaged API file: {data_path}"]
    if not gzip_path.is_file():
        return [*errors, f"missing packaged gzip file: {gzip_path}"]

    numeric_expectations = {
        "bytes": data_path.stat().st_size,
        "gzip_bytes": gzip_path.stat().st_size,
        "lines": count_lines(data_path),
        "records": count_records(data_path),
    }
    for key, expected_value in numeric_expectations.items():
        if entry.get(key) != expected_value:
            errors.append(
                f"manifest entry for {relative_path} has {entry.get(key)} {key}; "
                f"expected {expected_value}"
            )

    hash_expectations = {
        "sha256": sha256_file(data_path),
        "gzip_sha256": sha256_file(gzip_path),
    }
    for key, expected_value in hash_expectations.items():
        if entry.get(key) != expected_value:
            errors.append(f"manifest entry for {relative_path} has an invalid {key}")

    try:
        with gzip.open(gzip_path, "rb") as gzip_stream:
            decompressed_bytes = gzip_stream.read()
    except OSError as error:
        errors.append(f"packaged gzip file cannot be read for {relative_path}: {error}")
    else:
        if decompressed_bytes != data_path.read_bytes():
            errors.append(f"packaged gzip file does not match source file: {relative_path}")

    return errors


def main() -> int:
    return fail("pages-artifact-check", validate_pages_artifact())


if __name__ == "__main__":
    raise SystemExit(main())
