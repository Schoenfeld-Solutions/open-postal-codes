from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_smoke


def test_data_files_were_moved_to_public_versioned_api_root() -> None:
    assert Path("data/public/v1/at/post_code.csv").exists()
    assert Path("data/public/v1/at/post_code.json").exists()
    assert Path("data/public/v1/at/post_code.xml").exists()
    assert Path("data/public/v1/ch/post_code.csv").exists()
    assert Path("data/public/v1/ch/post_code.json").exists()
    assert Path("data/public/v1/ch/post_code.xml").exists()
    assert Path("data/public/v1/de/post_code.csv").exists()
    assert Path("data/public/v1/de/post_code.json").exists()
    assert Path("data/public/v1/de/post_code.xml").exists()
    assert Path("data/sources/geofabrik-regions.json").exists()
    assert not Path("data/public/v1/de/osm/streets.csv").exists()
    assert not Path("data/public/v1/li/communes.csv").exists()


def test_legacy_pipeline_files_are_removed() -> None:
    assert not Path("azure-pipelines.yml").exists()
    assert not Path(".github/workflows/create-osm-update.yaml").exists()


def test_local_guidance_files_are_gitignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "AGENTS.md" in gitignore
    assert "AGENTS.override.md" in gitignore
    assert "*.osm.pbf" in gitignore
    assert "*.osm.pbf.part" in gitignore


def test_repository_checks_pass() -> None:
    from tools.repo_checks import all_checks, language_policy_check

    assert language_policy_check.main() == 0
    assert all_checks.main() == 0
