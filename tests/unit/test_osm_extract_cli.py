from __future__ import annotations

from pathlib import Path

import pytest

from open_postal_codes.osm_extract import ExtractionError, extract_region_to_csv, main
from tests.unit.osm_fixture_builder import (
    boundary_fixture,
    closed_way,
    nodes,
    tagged_node,
    write_osm,
)

pytestmark = pytest.mark.unit


def test_extract_region_to_csv_writes_normalized_output(tmp_path: Path) -> None:
    input_path = tmp_path / "input.osm"
    output_path = tmp_path / "post_code.csv"
    write_osm(
        input_path,
        boundary_fixture(
            "\n".join(
                [
                    nodes(30, [(1, 1), (1, 4), (4, 4), (4, 1)]),
                    closed_way(
                        130,
                        30,
                        {
                            "boundary": "postal_code",
                            "postal_code_level": "8",
                            "postal_code": "28195",
                            "note": "28195 Bremen",
                        },
                    ),
                ]
            )
        ),
    )

    result = extract_region_to_csv(input_path, output_path)

    assert len(result.records) == 1
    assert output_path.read_text(encoding="utf-8").startswith("code,city,country,state,county")


def test_extract_cli_prints_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "input.osm"
    output_path = tmp_path / "post_code.csv"
    write_osm(
        input_path,
        boundary_fixture(
            "\n".join(
                [
                    tagged_node(300, 2, 2, {"addr:postcode": "33333", "addr:city": "Fallback"}),
                    tagged_node(301, 2.1, 2, {"addr:postcode": "33333", "addr:city": "Fallback"}),
                    tagged_node(302, 2.2, 2, {"addr:postcode": "33333", "addr:city": "Fallback"}),
                ]
            )
        ),
    )

    assert main([str(input_path), str(output_path)]) == 0

    assert "Extracted post codes: 1 records" in capsys.readouterr().out


def test_extract_rejects_file_without_country_boundary(tmp_path: Path) -> None:
    input_path = tmp_path / "missing-boundary.osm"
    write_osm(
        input_path,
        tagged_node(300, 2, 2, {"addr:postcode": "33333", "addr:city": "Fallback"}),
    )

    with pytest.raises(ExtractionError, match="administrative boundary"):
        extract_region_to_csv(input_path, tmp_path / "post_code.csv")
