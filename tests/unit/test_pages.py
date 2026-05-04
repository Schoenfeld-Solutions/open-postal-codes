from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from open_postal_codes.pages import main, package_pages_site
from open_postal_codes.post_code import PostCodeRecord, write_public_post_code_files
from tools.repo_checks.pages_contract_check import validate_public_records

pytestmark = pytest.mark.unit


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def write_source_metadata(repository_root: Path, generated_at: str) -> None:
    metadata_path = repository_root / "data/sources/geofabrik-regions.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "source": "Geofabrik D-A-CH PBF files",
                "regions": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_public_files(repository_root: Path) -> None:
    write_public_post_code_files([], repository_root / "data/public/v1/at")
    write_public_post_code_files([], repository_root / "data/public/v1/ch")
    write_public_post_code_files(
        [
            PostCodeRecord(code="28195", city="Bremen", state="Bremen", county="Bremen"),
            PostCodeRecord(
                code="66111",
                city="Saarbruecken",
                state="Saarland",
                county="Regionalverband",
            ),
        ],
        repository_root / "data/public/v1/de",
    )


def test_package_pages_site_publishes_api_files_manifest_and_gzip(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    output_root = tmp_path / "out"

    write_text(repository_root / "site" / "index.html", "<!doctype html><title>Open</title>")
    write_text(repository_root / "site" / "404.html", "<!doctype html><title>Missing</title>")
    write_source_metadata(repository_root, "2026-04-27T03:00:00Z")
    write_public_files(repository_root)

    result = package_pages_site(
        repository_root=repository_root,
        output_root=output_root,
        generated_at=datetime(2026, 4, 28, tzinfo=UTC),
    )

    manifest = read_json(result.manifest_path)
    paths = {entry["path"] for entry in manifest["files"]}
    media_types = {entry["path"]: entry["media_type"] for entry in manifest["files"]}

    assert result.manifest_path == output_root / "api/v1/index.json"
    assert (output_root / "index.html").exists()
    assert (output_root / "404.html").exists()
    assert paths == {
        "at/post_code.csv",
        "at/post_code.json",
        "at/post_code.xml",
        "ch/post_code.csv",
        "ch/post_code.json",
        "ch/post_code.xml",
        "de/post_code.csv",
        "de/post_code.json",
        "de/post_code.xml",
    }
    assert media_types == {
        "at/post_code.csv": "text/csv; charset=utf-8",
        "at/post_code.json": "application/json; charset=utf-8",
        "at/post_code.xml": "application/xml; charset=utf-8",
        "ch/post_code.csv": "text/csv; charset=utf-8",
        "ch/post_code.json": "application/json; charset=utf-8",
        "ch/post_code.xml": "application/xml; charset=utf-8",
        "de/post_code.csv": "text/csv; charset=utf-8",
        "de/post_code.json": "application/json; charset=utf-8",
        "de/post_code.xml": "application/xml; charset=utf-8",
    }
    assert manifest["generated_at"] == "2026-04-28T00:00:00Z"
    assert manifest["data_refreshed_at"] == "2026-04-27T03:00:00Z"
    assert manifest["base_path"] == "/open-postal-codes/api/v1/"
    assert "Geofabrik GmbH" in manifest["attribution"]
    assert {entry["path"]: entry["records"] for entry in manifest["files"]} == {
        "at/post_code.csv": 0,
        "at/post_code.json": 0,
        "at/post_code.xml": 0,
        "ch/post_code.csv": 0,
        "ch/post_code.json": 0,
        "ch/post_code.xml": 0,
        "de/post_code.csv": 2,
        "de/post_code.json": 2,
        "de/post_code.xml": 2,
    }

    gzip_path = output_root / "api/v1/de/post_code.csv.gz"
    with gzip.open(gzip_path, "rt", encoding="utf-8") as stream:
        assert stream.read().startswith(
            "code,city,country,state,county,time_zone,"
            "is_primary_location,location_rank,postal_code_rank,source,evidence_count"
        )


def test_package_pages_site_keeps_generated_files_outside_repository_data_root(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    output_root = tmp_path / "out"

    write_text(repository_root / "site" / "index.html", "index")
    write_text(repository_root / "site" / "404.html", "missing")
    write_public_files(repository_root)

    package_pages_site(repository_root=repository_root, output_root=output_root)

    assert not list((repository_root / "data/public/v1").rglob("*.gz"))
    assert (output_root / "api/v1/index.json").exists()


def test_package_pages_site_uses_null_data_refresh_time_without_source_metadata(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    output_root = tmp_path / "out"

    write_text(repository_root / "site" / "index.html", "index")
    write_text(repository_root / "site" / "404.html", "missing")
    write_public_files(repository_root)

    result = package_pages_site(
        repository_root=repository_root,
        output_root=output_root,
        generated_at=datetime(2026, 4, 28, tzinfo=UTC),
    )

    manifest = read_json(result.manifest_path)

    assert manifest["generated_at"] == "2026-04-28T00:00:00Z"
    assert manifest["data_refreshed_at"] is None


def test_pages_cli_packages_site(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repository_root = tmp_path / "repo"
    output_root = tmp_path / "out"

    write_text(repository_root / "site" / "index.html", "index")
    write_text(repository_root / "site" / "404.html", "missing")
    write_public_files(repository_root)

    assert main(["--repository-root", str(repository_root), "--output-root", str(output_root)]) == 0

    assert "Packaged 9 API files" in capsys.readouterr().out
    assert (output_root / "api/v1/index.json").exists()


def test_pages_contract_check_accepts_valid_ranked_records(tmp_path: Path) -> None:
    assert validate_public_records(valid_contract_rows(), tmp_path / "post_code.csv") == []


def test_pages_contract_check_rejects_multiple_primary_locations_for_one_post_code(
    tmp_path: Path,
) -> None:
    rows = valid_contract_rows()
    rows[1]["is_primary_location"] = "true"
    rows[1]["location_rank"] = "1"

    errors = validate_public_records(rows, tmp_path / "post_code.csv")

    assert any("primary locations" in error for error in errors)


def test_pages_contract_check_rejects_missing_primary_location(tmp_path: Path) -> None:
    rows = valid_contract_rows()
    rows[0]["is_primary_location"] = "false"

    errors = validate_public_records(rows, tmp_path / "post_code.csv")

    assert any("do not have a primary location" in error for error in errors)


def test_pages_contract_check_rejects_non_contiguous_location_ranks(tmp_path: Path) -> None:
    rows = valid_contract_rows()
    rows[1]["location_rank"] = "3"

    errors = validate_public_records(rows, tmp_path / "post_code.csv")

    assert any("non-contiguous location ranks" in error for error in errors)


def test_pages_contract_check_rejects_non_contiguous_postal_code_ranks(tmp_path: Path) -> None:
    rows = valid_contract_rows()
    rows[2]["postal_code_rank"] = "3"

    errors = validate_public_records(rows, tmp_path / "post_code.csv")

    assert any("non-contiguous postal code ranks" in error for error in errors)


def test_pages_contract_check_rejects_obsolete_primary_field(tmp_path: Path) -> None:
    rows = valid_contract_rows()
    rows[0]["is" + "_primary"] = "true"

    errors = validate_public_records(rows, tmp_path / "post_code.csv")

    assert any("obsolete primary field" in error for error in errors)


def valid_contract_rows() -> list[dict[str, str]]:
    return [
        {
            "code": "71540",
            "city": "Murrhardt",
            "country": "DE",
            "state": "Baden-Württemberg",
            "county": "Rems-Murr-Kreis",
            "time_zone": "W. Europe Standard Time",
            "is_primary_location": "true",
            "location_rank": "1",
            "postal_code_rank": "1",
            "source": "postal_boundary",
            "evidence_count": "4394",
        },
        {
            "code": "71540",
            "city": "Fichtenberg",
            "country": "DE",
            "state": "Baden-Württemberg",
            "county": "Landkreis Schwaebisch Hall",
            "time_zone": "W. Europe Standard Time",
            "is_primary_location": "false",
            "location_rank": "2",
            "postal_code_rank": "2",
            "source": "postal_boundary",
            "evidence_count": "4",
        },
        {
            "code": "74427",
            "city": "Fichtenberg",
            "country": "DE",
            "state": "Baden-Württemberg",
            "county": "Landkreis Schwaebisch Hall",
            "time_zone": "W. Europe Standard Time",
            "is_primary_location": "true",
            "location_rank": "1",
            "postal_code_rank": "1",
            "source": "postal_boundary",
            "evidence_count": "1149",
        },
    ]
