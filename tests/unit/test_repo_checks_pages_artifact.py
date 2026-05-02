from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from open_postal_codes.pages import package_pages_site
from open_postal_codes.post_code import PostCodeRecord, write_public_post_code_files
from tools.repo_checks import pages_artifact_check

pytestmark = pytest.mark.unit


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_manifest(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def write_fixture_public_data(repository_root: Path) -> None:
    write_public_post_code_files(
        [PostCodeRecord(code="28195", city="Bremen", state="Bremen")],
        repository_root / "data/public/v1/de",
    )
    write_public_post_code_files(
        [PostCodeRecord(code="1010", city="Wien", country="AT", state="Wien")],
        repository_root / "data/public/v1/at",
    )
    write_public_post_code_files(
        [PostCodeRecord(code="8001", city="Zürich", country="CH", state="Zürich")],
        repository_root / "data/public/v1/ch",
    )


def package_fixture(tmp_path: Path) -> Path:
    repository_root = tmp_path / "repo"
    output_root = tmp_path / "out"
    write_text(repository_root / "site/index.html", "<!doctype html><title>Open</title>")
    write_text(repository_root / "site/404.html", "<!doctype html><title>Missing</title>")
    write_text(repository_root / "site/assets/site.css", "body { color: #102033; }")
    write_text(repository_root / "site/assets/site.js", "document.title = document.title;")
    (repository_root / "site/favicon.ico").write_bytes(b"fixture")
    write_fixture_public_data(repository_root)
    package_pages_site(
        repository_root=repository_root,
        output_root=output_root,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return output_root


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_pages_artifact_check_accepts_valid_packaged_output(tmp_path: Path) -> None:
    output_root = package_fixture(tmp_path)

    assert pages_artifact_check.validate_packaged_output(output_root) == []


def test_pages_artifact_check_rejects_missing_api_file(tmp_path: Path) -> None:
    output_root = package_fixture(tmp_path)
    (output_root / "api/v1/at/post_code.csv").unlink()

    errors = pages_artifact_check.validate_packaged_output(output_root)

    assert any("missing packaged API file" in error for error in errors)


def test_pages_artifact_check_rejects_mismatched_manifest_count(tmp_path: Path) -> None:
    output_root = package_fixture(tmp_path)
    manifest_path = output_root / "api/v1/index.json"
    manifest = read_manifest(manifest_path)
    manifest["files"] = manifest["files"][:-1]
    write_manifest(manifest_path, manifest)

    errors = pages_artifact_check.validate_packaged_output(output_root)

    assert any("manifest lists 8 files; expected 9" in error for error in errors)


def test_pages_artifact_check_rejects_bad_gzip_hash(tmp_path: Path) -> None:
    output_root = package_fixture(tmp_path)
    (output_root / "api/v1/ch/post_code.json.gz").write_bytes(b"not a gzip file")

    errors = pages_artifact_check.validate_packaged_output(output_root)

    assert any("invalid gzip_sha256" in error for error in errors)
    assert any("cannot be read" in error for error in errors)


def test_pages_artifact_check_rejects_bad_record_count(tmp_path: Path) -> None:
    output_root = package_fixture(tmp_path)
    manifest_path = output_root / "api/v1/index.json"
    manifest = read_manifest(manifest_path)
    for entry in manifest["files"]:
        if entry["path"] == "de/post_code.csv":
            entry["records"] = 999
    write_manifest(manifest_path, manifest)

    errors = pages_artifact_check.validate_packaged_output(output_root)

    assert any("has 999 records; expected 1" in error for error in errors)
