"""Create local Business Central post code workbooks from public v1 data."""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ElementTree
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from open_postal_codes.countries import COUNTRY_CONFIGS, CountryConfig, get_country_config
from open_postal_codes.post_code import (
    PostCodeRecord,
    normalize_bool,
    normalize_text,
    read_post_code_csv,
)

DEFAULT_TEMPLATE_PATH = Path("tmp/private-outputs/input/PLZ.xlsx")
DEFAULT_OUTPUT_PATH = Path("tmp/private-outputs/export/PLZ_BusinessCentral_DACH.xlsx")
DEFAULT_GUARDRAILS_PATH = Path("tmp/private-outputs/export/PLZ_BusinessCentral_DACH_Guardrails.md")
DEFAULT_DATA_ROOT = Path("data/public/v1")
WORKSHEET_PATH = "xl/worksheets/sheet1.xml"
TABLE_PATH = "xl/tables/table1.xml"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
CELL_STYLE = "1"
BC_COLUMNS = (
    "Code",
    "Ort",
    "Suchbegriff (Ort)",
    "Länder-/Regionscode",
    "Bundesregion",
    "Zeitzone",
)
BC_FIELD_LIMITS = {
    "Code": 20,
    "Ort": 30,
    "Suchbegriff (Ort)": 30,
    "Länder-/Regionscode": 10,
    "Bundesregion": 30,
    "Zeitzone": 180,
}
NOTE_SUFFIX_PATTERN = re.compile(r"\s+is different from\b.*$", re.IGNORECASE)
NATURAL_BREAK_CHARACTERS = (" ", "-", "/", "\u2013", "\u2014")
TRAILING_FILLER_WORDS = {"bei", "b.", "an", "der", "mit", "von", "zu"}

ElementTree.register_namespace("x", SPREADSHEET_NS)
ElementTree.register_namespace("r", RELATIONSHIP_NS)


@dataclass(frozen=True)
class BusinessCentralRow:
    """One row in the local Business Central workbook."""

    code: str
    city: str
    search_city: str
    country: str
    state: str
    time_zone: str

    def values(self) -> tuple[str, str, str, str, str, str]:
        return (self.code, self.city, self.search_city, self.country, self.state, self.time_zone)


@dataclass(frozen=True)
class BusinessCentralExportResult:
    """Summary for a generated local Business Central workbook."""

    output_path: Path
    guardrails_path: Path
    source_records: int
    imported_records: int


def export_business_central(
    *,
    repository_root: Path,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    guardrails_path: Path = DEFAULT_GUARDRAILS_PATH,
    data_root: Path = DEFAULT_DATA_ROOT,
    countries: Sequence[CountryConfig] = COUNTRY_CONFIGS,
) -> BusinessCentralExportResult:
    """Generate the local D-A-CH Business Central workbook and guardrails file."""

    resolved_template_path = _resolve_path(repository_root, template_path)
    resolved_output_path = _resolve_path(repository_root, output_path)
    resolved_guardrails_path = _resolve_path(repository_root, guardrails_path)
    resolved_data_root = _resolve_path(repository_root, data_root)

    records = read_country_records(resolved_data_root, countries)
    rows = build_business_central_rows(records, countries=countries)
    write_business_central_workbook(
        template_path=resolved_template_path,
        output_path=resolved_output_path,
        rows=rows,
    )
    write_guardrails(
        path=resolved_guardrails_path,
        template_path=resolved_template_path,
        output_path=resolved_output_path,
        data_root=resolved_data_root,
        countries=countries,
        source_records=len(records),
        rows=rows,
    )
    return BusinessCentralExportResult(
        output_path=resolved_output_path,
        guardrails_path=resolved_guardrails_path,
        source_records=len(records),
        imported_records=len(rows),
    )


def read_country_records(
    data_root: Path,
    countries: Sequence[CountryConfig],
) -> tuple[PostCodeRecord, ...]:
    """Read public v1 records for the selected countries."""

    records: list[PostCodeRecord] = []
    for country in countries:
        csv_path = data_root / country.slug / "post_code.csv"
        if not csv_path.exists():
            raise ValueError(f"missing public post_code CSV: {csv_path}")
        records.extend(read_post_code_csv(csv_path))
    return tuple(records)


def build_business_central_rows(
    records: Iterable[PostCodeRecord],
    *,
    countries: Sequence[CountryConfig] = COUNTRY_CONFIGS,
) -> tuple[BusinessCentralRow, ...]:
    """Convert public v1 records into validated Business Central rows."""

    country_order = {country.code: index for index, country in enumerate(countries)}
    rows: list[BusinessCentralRow] = []
    keys: set[tuple[str, str]] = set()

    primary_records = (record for record in records if normalize_bool(record.is_primary_location))
    for record in sorted(
        primary_records,
        key=lambda value: (
            country_order.get(value.country, len(country_order)),
            value.code,
            value.city.casefold(),
            value.state.casefold(),
            value.county.casefold(),
        ),
    ):
        code = require_length(record.code, field_name="Code", limit=BC_FIELD_LIMITS["Code"])
        city = fit_business_central_text(
            record.city,
            field_name="Ort",
            limit=BC_FIELD_LIMITS["Ort"],
            required=True,
        )
        search_city = fit_business_central_text(
            city.upper(),
            field_name="Suchbegriff (Ort)",
            limit=BC_FIELD_LIMITS["Suchbegriff (Ort)"],
            required=True,
        )
        country = require_length(
            record.country,
            field_name="Länder-/Regionscode",
            limit=BC_FIELD_LIMITS["Länder-/Regionscode"],
        )
        state = fit_business_central_text(
            record.state,
            field_name="Bundesregion",
            limit=BC_FIELD_LIMITS["Bundesregion"],
            required=False,
        )
        time_zone = require_length(
            record.time_zone,
            field_name="Zeitzone",
            limit=BC_FIELD_LIMITS["Zeitzone"],
        )

        key = (code, city)
        if key in keys:
            raise ValueError(f"duplicate Business Central key: {code} {city}")
        keys.add(key)
        rows.append(
            BusinessCentralRow(
                code=code,
                city=city,
                search_city=search_city,
                country=country,
                state=state,
                time_zone=time_zone,
            )
        )
    return tuple(rows)


def require_length(value: str, *, field_name: str, limit: int) -> str:
    """Validate a required Business Central value length."""

    normalized = normalize_text(value)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > limit:
        raise ValueError(f"{field_name} exceeds Business Central length {limit}: {normalized}")
    return normalized


def fit_business_central_text(
    value: str,
    *,
    field_name: str,
    limit: int,
    required: bool,
) -> str:
    """Normalize and naturally shorten a Business Central text value."""

    normalized = NOTE_SUFFIX_PATTERN.sub("", normalize_text(value)).strip()
    if not normalized:
        if required:
            raise ValueError(f"{field_name} must not be empty")
        return ""
    if len(normalized) <= limit:
        return normalized

    shortened = shorten_at_natural_boundary(normalized, limit=limit)
    if not shortened and required:
        raise ValueError(f"{field_name} cannot be shortened safely: {normalized}")
    if len(shortened) > limit:
        raise ValueError(f"{field_name} exceeds Business Central length {limit}: {shortened}")
    return shortened


def shorten_at_natural_boundary(value: str, *, limit: int) -> str:
    """Shorten a value without cutting through the middle of a word."""

    cut_index = -1
    for character in NATURAL_BREAK_CHARACTERS:
        candidate = value.rfind(character, 0, limit + 1)
        if candidate > cut_index:
            cut_index = candidate
    if cut_index <= 0:
        raise ValueError(f"value cannot be shortened safely to {limit} characters: {value}")

    shortened = value[:cut_index].strip(" -/\u2013\u2014")
    return strip_trailing_fillers(shortened)


def strip_trailing_fillers(value: str) -> str:
    """Remove dangling trailing words after natural shortening."""

    parts = value.split()
    while parts and parts[-1].casefold() in TRAILING_FILLER_WORDS:
        parts.pop()
    return " ".join(parts)


def write_business_central_workbook(
    *,
    template_path: Path,
    output_path: Path,
    rows: Sequence[BusinessCentralRow],
) -> None:
    """Patch a local Business Central XLSX template with row values."""

    if not template_path.exists():
        raise ValueError(f"Business Central template does not exist: {template_path}")
    if template_path.resolve() == output_path.resolve():
        raise ValueError("Business Central output path must differ from the template path")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    replaced_parts: set[str] = set()
    with (
        zipfile.ZipFile(template_path, "r") as source,
        zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as target,
    ):
        for item in source.infolist():
            payload = source.read(item.filename)
            if item.filename == WORKSHEET_PATH:
                payload = build_worksheet_xml(payload, rows)
                replaced_parts.add(item.filename)
            elif item.filename == TABLE_PATH:
                payload = build_table_xml(payload, len(rows))
                replaced_parts.add(item.filename)
            target.writestr(item, payload)

    missing_parts = {WORKSHEET_PATH, TABLE_PATH}.difference(replaced_parts)
    if missing_parts:
        output_path.unlink(missing_ok=True)
        raise ValueError(f"Business Central template is missing parts: {', '.join(missing_parts)}")


def build_worksheet_xml(template_xml: bytes, rows: Sequence[BusinessCentralRow]) -> bytes:
    """Return patched worksheet XML for the Business Central workbook."""

    root = ElementTree.fromstring(template_xml)
    sheet_data = root.find(f"{{{SPREADSHEET_NS}}}sheetData")
    if sheet_data is None:
        raise ValueError("Business Central template worksheet has no sheetData")
    sheet_data.clear()
    sheet_data.append(make_row(1, ("00. BASIC", "PLZ", "225")))
    sheet_data.append(make_row(3, BC_COLUMNS))

    data_rows = rows or (BusinessCentralRow("", "", "", "", "", ""),)
    for offset, row in enumerate(data_rows, start=4):
        sheet_data.append(make_row(offset, row.values()))

    return xml_bytes(root)


def build_table_xml(template_xml: bytes, row_count: int) -> bytes:
    """Return patched table XML with the correct data range."""

    root = ElementTree.fromstring(template_xml)
    last_row = max(4, row_count + 3)
    reference = f"A3:F{last_row}"
    root.set("ref", reference)
    auto_filter = root.find(f"{{{SPREADSHEET_NS}}}autoFilter")
    if auto_filter is not None:
        auto_filter.set("ref", reference)
    return xml_bytes(root)


def make_row(row_number: int, values: Sequence[str]) -> ElementTree.Element:
    row = ElementTree.Element(f"{{{SPREADSHEET_NS}}}row", {"r": str(row_number)})
    for index, value in enumerate(values):
        row.append(make_inline_string_cell(cell_reference(index, row_number), value))
    return row


def make_inline_string_cell(reference: str, value: str) -> ElementTree.Element:
    cell = ElementTree.Element(
        f"{{{SPREADSHEET_NS}}}c",
        {"r": reference, "s": CELL_STYLE, "t": "inlineStr"},
    )
    inline_string = ElementTree.SubElement(cell, f"{{{SPREADSHEET_NS}}}is")
    text = ElementTree.SubElement(
        inline_string,
        f"{{{SPREADSHEET_NS}}}t",
        {f"{{{XML_NS}}}space": "preserve"},
    )
    text.text = value
    return cell


def cell_reference(column_index: int, row_number: int) -> str:
    if column_index < 0 or column_index >= 26:
        raise ValueError("column_index must be in the range A:Z")
    return f"{chr(ord('A') + column_index)}{row_number}"


def xml_bytes(root: ElementTree.Element) -> bytes:
    return cast(bytes, ElementTree.tostring(root, encoding="utf-8", xml_declaration=True))


def write_guardrails(
    *,
    path: Path,
    template_path: Path,
    output_path: Path,
    data_root: Path,
    countries: Sequence[CountryConfig],
    source_records: int,
    rows: Sequence[BusinessCentralRow],
) -> None:
    """Write an ignored local guardrails report next to the workbook."""

    path.parent.mkdir(parents=True, exist_ok=True)
    country_codes = ", ".join(country.code for country in countries)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    content = f"""# PLZ_BusinessCentral_DACH Guardrails

This file documents the local derivation for `{output_path.name}`. The workbook stays under
`tmp/private-outputs/export/` and is not a versioned repository contract.

## Sources

- Template: `{template_path}`
- Data root: `{data_root}`
- Countries: `{country_codes}`
- Business Central target: table 225 `Post Code`

## Import Scope

- Generated at: `{generated_at}`
- Public source rows: `{source_records}`
- Imported primary rows: `{len(rows)}`
- Unique Business Central keys `(Code, Ort)`: `{len({(row.code, row.city) for row in rows})}`

## Field Mapping

- `Code`: source `code`, BC `Code[20]`, required.
- `Ort`: source `city`, BC `Text[30]`, required.
- `Suchbegriff (Ort)`: uppercase `Ort`, BC `Code[30]`.
- `Länder-/Regionscode`: source `country`, BC `Code[10]`.
- `Bundesregion`: source `state`, BC `Text[30]`.
- `Zeitzone`: source `time_zone`, BC `Text[180]`.

## Validation

- Only rows with `is_primary_location=true` are imported.
- All Business Central field lengths are validated before writing the workbook.
- Duplicate `(Code, Ort)` keys fail generation.
- The XLSX template is patched only in `{WORKSHEET_PATH}` and `{TABLE_PATH}`.
"""
    path.write_text(content, encoding="utf-8")


def _resolve_path(repository_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repository_root / path


def parse_countries(value: str) -> tuple[CountryConfig, ...]:
    requested = tuple(part.strip() for part in value.split(",") if part.strip())
    if not requested:
        raise ValueError("countries must not be empty")
    return tuple(get_country_config(country) for country in requested)


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--template-path", type=Path, default=DEFAULT_TEMPLATE_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--guardrails-path", type=Path, default=DEFAULT_GUARDRAILS_PATH)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--countries",
        default="de,at,ch",
        help="Comma-separated country slugs or ISO codes. Defaults to de,at,ch.",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = parse_arguments(arguments)
    try:
        countries = parse_countries(parsed_arguments.countries)
        result = export_business_central(
            repository_root=parsed_arguments.repository_root,
            template_path=parsed_arguments.template_path,
            output_path=parsed_arguments.output_path,
            guardrails_path=parsed_arguments.guardrails_path,
            data_root=parsed_arguments.data_root,
            countries=countries,
        )
    except ValueError as error:
        print(f"Business Central export failed: {error}", file=sys.stderr)
        return 1

    print(
        "Business Central export completed: "
        f"{result.imported_records} imported rows from {result.source_records} source records, "
        f"workbook {result.output_path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
