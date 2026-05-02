from __future__ import annotations

import xml.etree.ElementTree as ElementTree
import zipfile
from pathlib import Path

import pytest

from open_postal_codes.business_central import (
    SPREADSHEET_NS,
    BusinessCentralRow,
    build_business_central_rows,
    build_table_xml,
    build_worksheet_xml,
    cell_reference,
    export_business_central,
    fit_business_central_text,
    main,
    parse_countries,
    read_country_records,
    require_length,
    shorten_at_natural_boundary,
    write_business_central_workbook,
)
from open_postal_codes.post_code import PostCodeRecord, write_public_post_code_files

pytestmark = pytest.mark.unit


def test_build_business_central_rows_uses_primary_state_and_country_values() -> None:
    rows = build_business_central_rows(
        [
            PostCodeRecord(
                code="73312",
                city="Geislingen an der Steige mit Berneck",
                state="Baden-Württemberg",
                county="Landkreis Göppingen",
                is_primary_location=True,
                location_rank=1,
                postal_code_rank=1,
            ),
            PostCodeRecord(
                code="73312",
                city="Secondary",
                state="Baden-Württemberg",
                county="Landkreis Göppingen",
                is_primary_location=False,
                location_rank=2,
                postal_code_rank=1,
            ),
            PostCodeRecord(
                code="1010",
                city="Wien",
                country="AT",
                state="Wien",
                county="Wien",
                is_primary_location=True,
                location_rank=1,
                postal_code_rank=1,
            ),
            PostCodeRecord(
                code="8001",
                city="Zuerich",
                country="CH",
                state="Kanton Zuerich",
                county="Bezirk Zuerich",
                is_primary_location=True,
                location_rank=1,
                postal_code_rank=1,
            ),
        ]
    )

    assert [row.values() for row in rows] == [
        (
            "73312",
            "Geislingen an der Steige",
            "GEISLINGEN AN DER STEIGE",
            "DE",
            "Baden-Württemberg",
            "W. Europe Standard Time",
        ),
        ("1010", "Wien", "WIEN", "AT", "Wien", "W. Europe Standard Time"),
        (
            "8001",
            "Zuerich",
            "ZUERICH",
            "CH",
            "Kanton Zuerich",
            "W. Europe Standard Time",
        ),
    ]


def test_build_business_central_rows_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_business_central_rows(
            [
                PostCodeRecord(
                    code="1010",
                    city="Wien",
                    country="AT",
                    state="Wien",
                    is_primary_location=True,
                    location_rank=1,
                    postal_code_rank=1,
                ),
                PostCodeRecord(
                    code="1010",
                    city="Wien",
                    country="AT",
                    state="Wien",
                    county="Bezirk",
                    is_primary_location=True,
                    location_rank=2,
                    postal_code_rank=1,
                ),
            ]
        )


def test_write_business_central_workbook_patches_template_parts(tmp_path: Path) -> None:
    template_path = tmp_path / "PLZ.xlsx"
    output_path = tmp_path / "PLZ_BusinessCentral_DACH.xlsx"
    write_template(template_path)

    write_business_central_workbook(
        template_path=template_path,
        output_path=output_path,
        rows=(
            BusinessCentralRow("1010", "Wien", "WIEN", "AT", "Wien", "W. Europe Standard Time"),
            BusinessCentralRow(
                "8001",
                "Zuerich",
                "ZUERICH",
                "CH",
                "Kanton Zuerich",
                "W. Europe Standard Time",
            ),
        ),
    )

    with zipfile.ZipFile(output_path, "r") as workbook:
        worksheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        table = ElementTree.fromstring(workbook.read("xl/tables/table1.xml"))

    assert table.get("ref") == "A3:F5"
    auto_filter = table.find(f"{{{SPREADSHEET_NS}}}autoFilter")
    assert auto_filter is not None
    assert auto_filter.get("ref") == "A3:F5"
    assert worksheet_values(worksheet)[4] == [
        "1010",
        "Wien",
        "WIEN",
        "AT",
        "Wien",
        "W. Europe Standard Time",
    ]
    assert worksheet_values(worksheet)[5] == [
        "8001",
        "Zuerich",
        "ZUERICH",
        "CH",
        "Kanton Zuerich",
        "W. Europe Standard Time",
    ]


def test_export_business_central_reads_dach_public_files(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    template_path = repository_root / "tmp/private-outputs/input/PLZ.xlsx"
    write_template(template_path)
    write_public_post_code_files(
        [PostCodeRecord(code="28195", city="Bremen", state="Bremen", county="Bremen")],
        repository_root / "data/public/v1/de",
    )
    write_public_post_code_files(
        [PostCodeRecord(code="1010", city="Wien", country="AT", state="Wien", county="Wien")],
        repository_root / "data/public/v1/at",
    )
    write_public_post_code_files(
        [
            PostCodeRecord(
                code="8001",
                city="Zuerich",
                country="CH",
                state="Kanton Zuerich",
                county="Bezirk Zuerich",
            )
        ],
        repository_root / "data/public/v1/ch",
    )

    result = export_business_central(repository_root=repository_root)

    assert result.source_records == 3
    assert result.imported_records == 3
    assert (
        result.output_path
        == repository_root / "tmp/private-outputs/export/PLZ_BusinessCentral_DACH.xlsx"
    )
    assert result.output_path.exists()
    assert result.guardrails_path.exists()


def test_read_country_records_rejects_missing_public_csv(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing public"):
        read_country_records(tmp_path, countries=parse_countries("de"))


def test_business_central_text_helpers_validate_required_values() -> None:
    assert (
        fit_business_central_text(
            "Postal area is different from source note",
            field_name="Ort",
            limit=30,
            required=True,
        )
        == "Postal area"
    )
    assert fit_business_central_text("", field_name="Bundesregion", limit=30, required=False) == ""

    with pytest.raises(ValueError, match="must not be empty"):
        require_length("", field_name="Code", limit=20)
    with pytest.raises(ValueError, match="exceeds"):
        require_length("x" * 21, field_name="Code", limit=20)
    with pytest.raises(ValueError, match="must not be empty"):
        fit_business_central_text("", field_name="Ort", limit=30, required=True)
    with pytest.raises(ValueError, match="cannot be shortened"):
        shorten_at_natural_boundary("X" * 31, limit=30)


def test_workbook_writer_rejects_missing_or_invalid_template(tmp_path: Path) -> None:
    missing_template = tmp_path / "missing.xlsx"
    output_path = tmp_path / "out.xlsx"

    with pytest.raises(ValueError, match="does not exist"):
        write_business_central_workbook(
            template_path=missing_template,
            output_path=output_path,
            rows=(),
        )

    write_template(output_path)
    with pytest.raises(ValueError, match="must differ"):
        write_business_central_workbook(
            template_path=output_path,
            output_path=output_path,
            rows=(),
        )


def test_workbook_writer_deletes_output_when_template_parts_are_missing(tmp_path: Path) -> None:
    template_path = tmp_path / "missing-table.xlsx"
    output_path = tmp_path / "out.xlsx"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", TEMPLATE_WORKSHEET_XML)

    with pytest.raises(ValueError, match="missing parts"):
        write_business_central_workbook(
            template_path=template_path,
            output_path=output_path,
            rows=(),
        )

    assert not output_path.exists()


def test_workbook_xml_helpers_cover_empty_rows_and_missing_autofilter() -> None:
    worksheet = ElementTree.fromstring(build_worksheet_xml(TEMPLATE_WORKSHEET_XML, ()))
    assert worksheet_values(worksheet)[4] == ["", "", "", "", "", ""]

    table_xml = f"""<?xml version="1.0" encoding="utf-8"?>
<x:table xmlns:x="{SPREADSHEET_NS}" id="5" name="Table5" displayName="Table5" ref="A3:F4">
  <x:tableColumns count="6" />
</x:table>
""".encode()
    table = ElementTree.fromstring(build_table_xml(table_xml, 0))
    assert table.get("ref") == "A3:F4"

    with pytest.raises(ValueError, match="no sheetData"):
        build_worksheet_xml(f'<x:worksheet xmlns:x="{SPREADSHEET_NS}" />'.encode(), ())
    with pytest.raises(ValueError, match="range A:Z"):
        cell_reference(26, 1)


def test_business_central_cli_reports_success_and_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root = tmp_path / "repo"
    template_path = repository_root / "tmp/private-outputs/input/PLZ.xlsx"
    write_template(template_path)
    write_public_post_code_files(
        [PostCodeRecord(code="28195", city="Bremen", state="Bremen")],
        repository_root / "data/public/v1/de",
    )

    assert main(["--repository-root", str(repository_root), "--countries", "de"]) == 0
    assert "Business Central export completed" in capsys.readouterr().out

    assert main(["--repository-root", str(repository_root), "--countries", ""]) == 1
    assert "Business Central export failed" in capsys.readouterr().err


def write_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", TEMPLATE_WORKSHEET_XML)
        workbook.writestr("xl/tables/table1.xml", TEMPLATE_TABLE_XML)
        workbook.writestr("[Content_Types].xml", "")


def worksheet_values(root: ElementTree.Element) -> dict[int, list[str]]:
    values: dict[int, list[str]] = {}
    for row in root.findall(f".//{{{SPREADSHEET_NS}}}row"):
        row_number = int(row.get("r", "0"))
        values[row_number] = [text.text or "" for text in row.findall(f".//{{{SPREADSHEET_NS}}}t")]
    return values


TEMPLATE_WORKSHEET_XML = f"""<?xml version="1.0" encoding="utf-8"?>
<x:worksheet xmlns:x="{SPREADSHEET_NS}">
  <x:sheetData>
    <x:row r="1" />
    <x:row r="3" />
    <x:row r="4" />
  </x:sheetData>
  <x:tableParts count="1" />
</x:worksheet>
""".encode()

TEMPLATE_TABLE_XML = f"""<?xml version="1.0" encoding="utf-8"?>
<x:table xmlns:x="{SPREADSHEET_NS}" id="5" name="Table5" displayName="Table5" ref="A3:F4">
  <x:autoFilter ref="A3:F4" />
  <x:tableColumns count="6" />
</x:table>
""".encode()
