"""Check static Pages API sources and packaging contract."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, cast

from open_postal_codes.pages import DATA_FILES
from open_postal_codes.post_code import POST_CODE_FIELDS
from tools.repo_checks.common import fail


def read_header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as stream:
        return next(csv.reader(stream))


def main() -> int:
    errors: list[str] = []
    data_root = Path("data/public/v1")
    expected_paths = {
        "de/post_code.csv",
        "de/post_code.json",
        "de/post_code.xml",
    }

    data_file_paths = {relative_path for _, relative_path, _, _ in DATA_FILES}
    if data_file_paths != expected_paths:
        errors.append("Pages DATA_FILES does not match the post_code v1 contract")

    for relative_path in expected_paths:
        source_path = data_root / relative_path
        if not source_path.exists():
            errors.append(f"missing API source file: {source_path}")

    csv_path = data_root / "de/post_code.csv"
    if csv_path.exists() and tuple(read_header(csv_path)) != POST_CODE_FIELDS:
        errors.append(f"{csv_path} has an unexpected CSV header")

    json_path = data_root / "de/post_code.json"
    if json_path.exists():
        payload = cast(dict[str, Any], json.loads(json_path.read_text(encoding="utf-8")))
        if payload.get("title") != "post_code" or not isinstance(payload.get("records"), list):
            errors.append(f"{json_path} does not match the post_code JSON contract")

    xml_path = data_root / "de/post_code.xml"
    if xml_path.exists() and ElementTree.parse(xml_path).getroot().tag != "post_code":
        errors.append(f"{xml_path} does not match the post_code XML contract")

    forbidden_public_files = (
        data_root / "de/osm/streets.csv",
        data_root / "de/osm/streets.raw.csv",
        data_root / "de/osm/streets.ignore.csv",
        data_root / "li/communes.csv",
    )
    for path in forbidden_public_files:
        if path.exists():
            errors.append(f"obsolete API source file still exists: {path}")

    if list(data_root.rglob("*.gz")):
        errors.append("gzip downloads must be generated into the Pages artifact, not tracked data")

    return fail("pages-contract-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
