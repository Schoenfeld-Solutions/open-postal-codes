"""Check import boundaries for the public data tooling."""

from __future__ import annotations

import ast
from pathlib import Path

from tools.repo_checks.common import fail

SOURCE_ROOT = Path("src/open_postal_codes")

COUNTRIES_ALLOWED_IMPORTS = {"__future__", "dataclasses", "re", "typing"}
POST_CODE_FORBIDDEN_IMPORTS = {
    "http",
    "open_postal_codes.business_central",
    "open_postal_codes.osm_extract",
    "open_postal_codes.pages",
    "open_postal_codes.refresh_data",
    "openpyxl",
    "osmium",
    "requests",
    "shapely",
    "urllib",
    "zipfile",
}
ORCHESTRATION_MODULES = {
    "business_central.py": {"open_postal_codes.pages", "open_postal_codes.refresh_data"},
    "pages.py": {"open_postal_codes.business_central", "open_postal_codes.refresh_data"},
    "refresh_data.py": {"open_postal_codes.business_central", "open_postal_codes.pages"},
}
PRODUCT_FORBIDDEN_IMPORTS = {"tests", "tools"}


def imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return tuple(imports)


def import_matches(module: str, forbidden: str) -> bool:
    return module == forbidden or module.startswith(f"{forbidden}.")


def validate_boundaries(source_root: Path = SOURCE_ROOT) -> list[str]:
    errors: list[str] = []
    if not source_root.exists():
        return errors

    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        modules = imported_modules(path)
        display_path = path.as_posix()

        for module in modules:
            if any(import_matches(module, forbidden) for forbidden in PRODUCT_FORBIDDEN_IMPORTS):
                errors.append(f"{display_path}: product code must not import {module}")

        if path.name == "countries.py":
            for module in modules:
                if module.split(".", maxsplit=1)[0] not in COUNTRIES_ALLOWED_IMPORTS:
                    errors.append(f"{display_path}: country configuration imports {module}")

        if path.name == "post_code.py":
            for module in modules:
                if any(
                    import_matches(module, forbidden) for forbidden in POST_CODE_FORBIDDEN_IMPORTS
                ):
                    errors.append(f"{display_path}: domain model imports {module}")

        forbidden_orchestration = ORCHESTRATION_MODULES.get(path.name, set())
        for module in modules:
            if any(import_matches(module, forbidden) for forbidden in forbidden_orchestration):
                errors.append(f"{display_path}: orchestration module imports {module}")

    return errors


def main() -> int:
    return fail("boundary-truth-check", validate_boundaries())


if __name__ == "__main__":
    raise SystemExit(main())
