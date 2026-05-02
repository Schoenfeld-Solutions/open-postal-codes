from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_postal_codes.countries import COUNTRY_CONFIGS
from open_postal_codes.post_code import PostCodeRecord, write_public_post_code_files
from tools.repo_checks import (
    boundary_truth_check,
    module_size_check,
    public_data_quality_check,
    reference_policy_check,
)

pytestmark = pytest.mark.unit


def write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * count, encoding="utf-8")


def test_module_size_check_accepts_small_modules(tmp_path: Path) -> None:
    write_lines(tmp_path / "src/open_postal_codes/example.py", 12)
    write_lines(tmp_path / "tests/unit/test_example.py", 12)
    write_lines(tmp_path / "tools/repo_checks/example_check.py", 12)

    assert module_size_check.validate_file_sizes(tmp_path) == []


def test_module_size_check_rejects_large_product_modules(tmp_path: Path) -> None:
    write_lines(
        tmp_path / "src/open_postal_codes/large.py",
        module_size_check.MAX_PRODUCT_LINES + 1,
    )

    errors = module_size_check.validate_file_sizes(tmp_path)

    assert errors == ["product module exceeds 650 lines: src/open_postal_codes/large.py (651)"]


def test_public_data_quality_accepts_complete_fixture(tmp_path: Path) -> None:
    write_public_data_quality_fixture(tmp_path)

    assert (
        public_data_quality_check.validate_public_data(
            tmp_path,
            minimum_records_by_country={"de": 1, "at": 1, "ch": 1},
            minimum_unique_post_codes_by_country={"de": 1, "at": 1, "ch": 1},
        )
        == []
    )


def test_public_data_quality_rejects_missing_state(tmp_path: Path) -> None:
    write_public_data_quality_fixture(
        tmp_path,
        records_by_country={
            "de": [PostCodeRecord(code="28195", city="Bremen", state="Bremen")],
            "at": [PostCodeRecord(code="1010", city="Wien", country="AT", state="Wien")],
            "ch": [PostCodeRecord(code="8001", city="Zürich", country="CH", state="")],
        },
    )

    errors = public_data_quality_check.validate_public_data(
        tmp_path,
        minimum_records_by_country={"de": 1, "at": 1, "ch": 1},
        minimum_unique_post_codes_by_country={"de": 1, "at": 1, "ch": 1},
    )

    assert any("without state" in error for error in errors)


def test_public_data_quality_rejects_low_record_count(tmp_path: Path) -> None:
    write_public_data_quality_fixture(tmp_path)

    errors = public_data_quality_check.validate_public_data(
        tmp_path,
        minimum_records_by_country={"de": 2, "at": 1, "ch": 1},
        minimum_unique_post_codes_by_country={"de": 1, "at": 1, "ch": 1},
    )

    assert any("expected at least 2" in error for error in errors)


def test_public_data_quality_rejects_low_unique_post_code_count(tmp_path: Path) -> None:
    write_public_data_quality_fixture(tmp_path)

    errors = public_data_quality_check.validate_public_data(
        tmp_path,
        minimum_records_by_country={"de": 1, "at": 1, "ch": 1},
        minimum_unique_post_codes_by_country={"de": 2, "at": 1, "ch": 1},
    )

    assert any("unique post codes" in error and "expected at least 2" in error for error in errors)


def test_public_data_quality_rejects_missing_metadata_key(tmp_path: Path) -> None:
    write_public_data_quality_fixture(tmp_path, omitted_metadata_key="ch/switzerland")

    errors = public_data_quality_check.validate_public_data(
        tmp_path,
        minimum_records_by_country={"de": 1, "at": 1, "ch": 1},
        minimum_unique_post_codes_by_country={"de": 1, "at": 1, "ch": 1},
    )

    assert errors == ["source metadata is missing keys: ch/switzerland"]


def test_public_data_quality_rejects_malformed_metadata_values(tmp_path: Path) -> None:
    write_public_data_quality_fixture(
        tmp_path,
        metadata_overrides={
            "at/austria": {
                "url": "https://example.test/austria.osm.pbf",
                "content_length": 0,
                "md5": "not-md5",
                "etag": "",
            }
        },
    )

    errors = public_data_quality_check.validate_public_data(
        tmp_path,
        minimum_records_by_country={"de": 1, "at": 1, "ch": 1},
        minimum_unique_post_codes_by_country={"de": 1, "at": 1, "ch": 1},
    )

    assert any("at/austria has unexpected url" in error for error in errors)
    assert any("at/austria must have positive content_length" in error for error in errors)
    assert any("at/austria must have a 32-character md5" in error for error in errors)
    assert any("at/austria has empty etag" in error for error in errors)


def test_public_data_quality_rejects_missing_sentinel_row(tmp_path: Path) -> None:
    write_public_data_quality_fixture(
        tmp_path,
        records_by_country={
            "de": [PostCodeRecord(code="28195", city="Bremen", state="Bremen")],
            "at": [PostCodeRecord(code="1010", city="Other", country="AT", state="Wien")],
            "ch": [PostCodeRecord(code="8001", city="Zürich", country="CH", state="Zürich")],
        },
    )

    errors = public_data_quality_check.validate_public_data(
        tmp_path,
        minimum_records_by_country={"de": 1, "at": 1, "ch": 1},
        minimum_unique_post_codes_by_country={"de": 1, "at": 1, "ch": 1},
    )

    assert any("1010 Wien" in error for error in errors)


def test_public_data_quality_rejects_sentinel_row_with_wrong_timezone(tmp_path: Path) -> None:
    write_public_data_quality_fixture(tmp_path)
    csv_path = tmp_path / "data/public/v1/at/post_code.csv"
    csv_path.write_text(
        csv_path.read_text(encoding="utf-8").replace("W. Europe Standard Time", "UTC"),
        encoding="utf-8",
    )

    errors = public_data_quality_check.validate_public_data(
        tmp_path,
        minimum_records_by_country={"de": 1, "at": 1, "ch": 1},
        minimum_unique_post_codes_by_country={"de": 1, "at": 1, "ch": 1},
    )

    assert any("1010 Wien with AT, state, and W. Europe Standard Time" in error for error in errors)


def test_public_data_quality_rejects_tracked_pbf_files() -> None:
    assert public_data_quality_check.validate_tracked_pbf_files(("austria.osm.pbf",)) == [
        "raw PBF downloads must not be tracked: austria.osm.pbf"
    ]


def test_boundary_truth_check_accepts_current_layering(tmp_path: Path) -> None:
    source_root = tmp_path / "src/open_postal_codes"
    source_root.mkdir(parents=True)
    (source_root / "countries.py").write_text(
        "from __future__ import annotations\nimport re\nfrom dataclasses import dataclass\n",
        encoding="utf-8",
    )
    (source_root / "post_code.py").write_text(
        "from open_postal_codes.countries import DEFAULT_COUNTRY_CONFIG\n",
        encoding="utf-8",
    )
    (source_root / "refresh_data.py").write_text(
        "from open_postal_codes.post_code import PostCodeRecord\n",
        encoding="utf-8",
    )

    assert boundary_truth_check.validate_boundaries(source_root) == []


def test_boundary_truth_check_rejects_domain_importing_network_code(tmp_path: Path) -> None:
    source_root = tmp_path / "src/open_postal_codes"
    source_root.mkdir(parents=True)
    (source_root / "post_code.py").write_text("import urllib.request\n", encoding="utf-8")

    errors = boundary_truth_check.validate_boundaries(source_root)

    assert errors == [
        f"{(source_root / 'post_code.py').as_posix()}: domain model imports urllib.request"
    ]


def test_boundary_truth_check_rejects_orchestration_cycles(tmp_path: Path) -> None:
    source_root = tmp_path / "src/open_postal_codes"
    source_root.mkdir(parents=True)
    (source_root / "refresh_data.py").write_text(
        "from open_postal_codes.pages import package_pages\n",
        encoding="utf-8",
    )

    errors = boundary_truth_check.validate_boundaries(source_root)

    assert errors == [
        f"{(source_root / 'refresh_data.py').as_posix()}: "
        "orchestration module imports open_postal_codes.pages"
    ]


def test_reference_policy_rejects_public_provenance_terms(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("Generated by " + "Cod" + "ex\n", encoding="utf-8")

    assert reference_policy_check.reference_errors_for_path(path) == [
        f"{path}: contains prohibited reference"
    ]


def test_reference_policy_allows_normal_project_words(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("This API is maintained as public data.\n", encoding="utf-8")

    assert reference_policy_check.reference_errors_for_path(path) == []


def write_public_data_quality_fixture(
    repository_root: Path,
    *,
    records_by_country: dict[str, list[PostCodeRecord]] | None = None,
    omitted_metadata_key: str | None = None,
    metadata_overrides: dict[str, dict[str, object]] | None = None,
) -> None:
    records = records_by_country or {
        "de": [PostCodeRecord(code="28195", city="Bremen", state="Bremen")],
        "at": [PostCodeRecord(code="1010", city="Wien", country="AT", state="Wien")],
        "ch": [PostCodeRecord(code="8001", city="Zürich", country="CH", state="Zürich")],
    }
    for country, country_records in records.items():
        write_public_post_code_files(
            country_records,
            repository_root / f"data/public/v1/{country}",
        )

    metadata_regions = {
        region.metadata_key: region
        for country in COUNTRY_CONFIGS
        for region in country.geofabrik_regions
    }
    metadata_keys = set(metadata_regions)
    if omitted_metadata_key is not None:
        metadata_keys.remove(omitted_metadata_key)
    metadata_overrides = metadata_overrides or {}
    metadata_path = repository_root / "data/sources/geofabrik-regions.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "regions": {
                    key: {
                        "url": metadata_regions[key].url,
                        "content_length": 1,
                        "etag": '"fixture"',
                        "last_modified": "Thu, 30 Apr 2026 01:28:05 GMT",
                        "md5": "900150983cd24fb0d6963f7d28e17f72",
                    }
                    | metadata_overrides.get(key, {})
                    for key in sorted(metadata_keys)
                }
            }
        ),
        encoding="utf-8",
    )
