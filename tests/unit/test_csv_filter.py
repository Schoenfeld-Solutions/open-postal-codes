from __future__ import annotations

from pathlib import Path

import pytest

from open_postal_codes.csv_filter import filter_csv, filter_rows, main

pytestmark = pytest.mark.unit


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_filter_csv_preserves_header_and_removes_exact_ignore_rows(tmp_path: Path) -> None:
    source = tmp_path / "streets.raw.csv"
    ignore = tmp_path / "streets.ignore.csv"
    output = tmp_path / "streets.csv"

    write_text(
        source,
        "\n".join(
            [
                "Name,PostalCode,Locality,RegionalKey,Borough,Suburb",
                "Keepstr.,12345,Example,01001001,,",
                "Ignorestr.,12345,Example,01001001,,",
                "",
            ]
        ),
    )
    write_text(
        ignore,
        "\n".join(
            [
                "Name,PostalCode,Locality,RegionalKey,Borough,Suburb",
                "Ignorestr.,12345,Example,01001001,,",
                "",
            ]
        ),
    )

    result = filter_csv(source, ignore, output)

    assert result.input_rows == 2
    assert result.ignored_rows == 1
    assert result.output_rows == 1
    assert output.read_text(encoding="utf-8") == (
        "Name,PostalCode,Locality,RegionalKey,Borough,Suburb\nKeepstr.,12345,Example,01001001,,\n"
    )


def test_filter_csv_keeps_unicode_and_quoted_values_stable(tmp_path: Path) -> None:
    source = tmp_path / "streets.raw.csv"
    ignore = tmp_path / "streets.ignore.csv"
    output = tmp_path / "streets.csv"

    write_text(
        source,
        (
            "Name,PostalCode,Locality,RegionalKey,Borough,Suburb\n"
            '"Am Mühlweg / Kriegersiedlung",35410,Hungen,06531008,Trais-Horloff,\n'
            '""" 7 Berge """,74921,Helmstadt-Bargen,08226106,,\n'
        ),
    )
    write_text(
        ignore,
        (
            "Name,PostalCode,Locality,RegionalKey,Borough,Suburb\n"
            '"Am Mühlweg / Kriegersiedlung",35410,Hungen,06531008,Trais-Horloff,\n'
        ),
    )

    result = filter_csv(source, ignore, output)

    assert result.ignored_rows == 1
    assert '" 7 Berge "' in output.read_text(encoding="utf-8")
    assert "Mühlweg" not in output.read_text(encoding="utf-8")


def test_filter_rows_reports_removed_rows() -> None:
    rows = [["keep"], ["remove"], ["keep-too"]]
    filtered_rows, removed_count = filter_rows(rows, {("remove",)})

    assert filtered_rows == [["keep"], ["keep-too"]]
    assert removed_count == 1


def test_csv_filter_cli_prints_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source.csv"
    ignore = tmp_path / "ignore.csv"
    output = tmp_path / "output.csv"
    write_text(source, "Name\nA\nB\n")
    write_text(ignore, "Name\nB\n")

    assert main([str(source), str(ignore), str(output)]) == 0

    assert "1 ignored rows" in capsys.readouterr().out
    assert output.read_text(encoding="utf-8") == "Name\nA\n"
