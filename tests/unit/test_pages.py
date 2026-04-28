from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from open_postal_codes.pages import main, package_pages_site

pytestmark = pytest.mark.unit


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_package_pages_site_publishes_api_files_manifest_and_gzip(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    output_root = tmp_path / "out"

    write_text(repository_root / "site" / "index.html", "<!doctype html><title>Open</title>")
    write_text(repository_root / "site" / "404.html", "<!doctype html><title>Missing</title>")
    write_text(
        repository_root / "data/public/v1/de/osm/streets.csv",
        "Name,PostalCode,Locality,RegionalKey,Borough,Suburb\nA,1,B,2,,\n",
    )
    write_text(
        repository_root / "data/public/v1/de/osm/streets.raw.csv",
        "Name,PostalCode,Locality,RegionalKey,Borough,Suburb\nA,1,B,2,,\nC,3,D,4,,\n",
    )
    write_text(
        repository_root / "data/public/v1/de/osm/streets.ignore.csv",
        "Name,PostalCode,Locality,RegionalKey,Borough,Suburb\nC,3,D,4,,\n",
    )
    write_text(
        repository_root / "data/public/v1/li/communes.csv",
        "Key,Name,ElectoralDistrict\n7001,Vaduz,Oberland\n",
    )

    result = package_pages_site(
        repository_root=repository_root,
        output_root=output_root,
        generated_at=datetime(2026, 4, 28, tzinfo=UTC),
    )

    manifest = read_json(result.manifest_path)
    paths = {entry["path"] for entry in manifest["files"]}

    assert result.manifest_path == output_root / "api/v1/index.json"
    assert (output_root / "index.html").exists()
    assert (output_root / "404.html").exists()
    assert paths == {
        "de/osm/streets.csv",
        "de/osm/streets.raw.csv",
        "de/osm/streets.ignore.csv",
        "li/communes.csv",
    }
    assert manifest["generated_at"] == "2026-04-28T00:00:00Z"
    assert manifest["base_path"] == "/open-postal-codes/api/v1/"

    gzip_path = output_root / "api/v1/de/osm/streets.csv.gz"
    with gzip.open(gzip_path, "rt", encoding="utf-8") as stream:
        assert stream.read().startswith("Name,PostalCode")


def test_package_pages_site_keeps_generated_files_outside_repository_data_root(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    output_root = tmp_path / "out"

    write_text(repository_root / "site" / "index.html", "index")
    write_text(repository_root / "site" / "404.html", "missing")
    for relative_path in (
        "de/osm/streets.csv",
        "de/osm/streets.raw.csv",
        "de/osm/streets.ignore.csv",
        "li/communes.csv",
    ):
        write_text(repository_root / "data/public/v1" / relative_path, "h\nv\n")

    package_pages_site(repository_root=repository_root, output_root=output_root)

    assert not list((repository_root / "data/public/v1").rglob("*.gz"))
    assert (output_root / "api/v1/index.json").exists()


def test_pages_cli_packages_site(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repository_root = tmp_path / "repo"
    output_root = tmp_path / "out"

    write_text(repository_root / "site" / "index.html", "index")
    write_text(repository_root / "site" / "404.html", "missing")
    for relative_path in (
        "de/osm/streets.csv",
        "de/osm/streets.raw.csv",
        "de/osm/streets.ignore.csv",
        "li/communes.csv",
    ):
        write_text(repository_root / "data/public/v1" / relative_path, "h\nv\n")

    assert main(["--repository-root", str(repository_root), "--output-root", str(output_root)]) == 0

    assert "Packaged 4 API files" in capsys.readouterr().out
    assert (output_root / "api/v1/index.json").exists()
