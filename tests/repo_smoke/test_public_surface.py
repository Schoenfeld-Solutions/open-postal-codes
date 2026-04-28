from __future__ import annotations

import pytest

import open_postal_codes

pytestmark = pytest.mark.repo_smoke


def test_package_root_exports_only_curated_surface() -> None:
    assert tuple(open_postal_codes.__all__) == (
        "PostCodeRecord",
        "dedupe_records",
    )


def test_package_root_does_not_export_cli_implementation_details() -> None:
    assert not hasattr(open_postal_codes, "parse_arguments")
    assert not hasattr(open_postal_codes, "gzip_csv")
    assert not hasattr(open_postal_codes, "package_pages_site")
