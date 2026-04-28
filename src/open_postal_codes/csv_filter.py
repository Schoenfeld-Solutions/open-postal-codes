"""Filter generated street CSV rows with a manually curated ignore list."""

from __future__ import annotations

import argparse
import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True)
class CsvFilterResult:
    """Summary for a completed CSV filtering run."""

    input_rows: int
    ignored_rows: int
    output_rows: int


def read_csv_rows(stream: TextIO) -> set[tuple[str, ...]]:
    """Read all rows from a CSV stream as exact tuple keys."""

    reader = csv.reader(stream, delimiter=",")
    return {tuple(row) for row in reader}


def filter_rows(
    rows: Iterable[list[str]], ignored_rows: set[tuple[str, ...]]
) -> tuple[list[list[str]], int]:
    """Return rows not present in the ignore set and the number removed."""

    output_rows: list[list[str]] = []
    removed_count = 0

    for row in rows:
        if tuple(row) in ignored_rows:
            removed_count += 1
            continue
        output_rows.append(row)

    return output_rows, removed_count


def filter_csv(source_path: Path, ignore_path: Path, output_path: Path) -> CsvFilterResult:
    """Write a filtered CSV while preserving the source header."""

    with ignore_path.open(mode="r", newline="", encoding="utf-8") as ignore_stream:
        ignored_rows = read_csv_rows(ignore_stream)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with (
        source_path.open(mode="r", newline="", encoding="utf-8") as source_stream,
        output_path.open(mode="w", newline="", encoding="utf-8") as output_stream,
    ):
        source_reader = csv.reader(source_stream, delimiter=",")
        output_writer = csv.writer(output_stream, delimiter=",", lineterminator="\n")

        header = next(source_reader)
        output_writer.writerow(header)

        input_count = 0
        output_count = 0
        ignored_count = 0

        for source_row in source_reader:
            input_count += 1
            if tuple(source_row) in ignored_rows:
                ignored_count += 1
                continue
            output_writer.writerow(source_row)
            output_count += 1

    return CsvFilterResult(
        input_rows=input_count,
        ignored_rows=ignored_count,
        output_rows=output_count,
    )


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Raw source CSV.")
    parser.add_argument("ignore", type=Path, help="CSV rows to remove.")
    parser.add_argument("output", type=Path, help="Filtered output CSV.")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = parse_arguments(arguments)
    result = filter_csv(
        parsed_arguments.source,
        parsed_arguments.ignore,
        parsed_arguments.output,
    )
    print(
        "Filtered CSV: "
        f"{result.input_rows} input rows, "
        f"{result.ignored_rows} ignored rows, "
        f"{result.output_rows} output rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
