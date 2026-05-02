from __future__ import annotations

from pathlib import Path

import pytest

from tools.repo_checks import workflow_policy_check

pytestmark = pytest.mark.unit


PULL_REQUEST_WORKFLOW = """\
name: Pull Request Gates

on:
  pull_request:
    branches:
      - main

permissions:
  contents: read
  pull-requests: read

concurrency:
  group: pull-request-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  quality:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - run: python3 -m pytest --cov=open_postal_codes --cov-fail-under=90
      - run: python3 -m ruff check .
      - run: python3 -m ruff format --check .
      - run: python3 -m mypy src tests tools
      - run: python3 -m tools.repo_checks.all_checks
      - run: python3 -m open_postal_codes.pages --output-root out
      - run: git diff --check
"""

DATA_REFRESH_WORKFLOW = """\
name: Refresh D-A-CH Post Code Data

on:
  schedule:
    - cron: "17 2 * * 1"
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: data-refresh-post-code
  cancel-in-progress: true

jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 240
    steps:
      - run: python3 -m open_postal_codes.refresh_data
      - run: python3 -m tools.repo_checks.all_checks
"""

PAGES_WORKFLOW = """\
name: Build and Publish GitHub Pages

on:
  push:
    branches:
      - main

permissions:
  contents: read

concurrency:
  group: github-pages-${{ github.ref }}
  cancel-in-progress: true

jobs:
  package-site:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: python3 -m open_postal_codes.pages --output-root out
"""


def write_workflows(
    repository_root: Path,
    *,
    pull_request_workflow: str = PULL_REQUEST_WORKFLOW,
    data_refresh_workflow: str = DATA_REFRESH_WORKFLOW,
    pages_workflow: str = PAGES_WORKFLOW,
) -> None:
    workflow_root = repository_root / ".github/workflows"
    workflow_root.mkdir(parents=True)
    (workflow_root / "pull-request.yml").write_text(pull_request_workflow, encoding="utf-8")
    (workflow_root / "data-refresh.yml").write_text(data_refresh_workflow, encoding="utf-8")
    (workflow_root / "pages.yml").write_text(pages_workflow, encoding="utf-8")


def test_workflow_policy_accepts_current_workflows() -> None:
    assert workflow_policy_check.validate_workflows(Path.cwd()) == []


def test_workflow_policy_accepts_compliant_fixture(tmp_path: Path) -> None:
    write_workflows(tmp_path)

    assert workflow_policy_check.validate_workflows(tmp_path) == []


def test_workflow_policy_rejects_missing_timeout(tmp_path: Path) -> None:
    write_workflows(
        tmp_path,
        pull_request_workflow=PULL_REQUEST_WORKFLOW.replace(
            "    timeout-minutes: 15\n",
            "",
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("job quality is missing timeout-minutes" in error for error in errors)


def test_workflow_policy_rejects_missing_permissions(tmp_path: Path) -> None:
    write_workflows(
        tmp_path,
        pages_workflow=PAGES_WORKFLOW.replace(
            "permissions:\n  contents: read\n\n",
            "",
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("pages.yml is missing top-level permissions" in error for error in errors)


def test_workflow_policy_rejects_pull_request_target(tmp_path: Path) -> None:
    write_workflows(
        tmp_path,
        pull_request_workflow=PULL_REQUEST_WORKFLOW.replace(
            "pull_request:", "pull_request_target:"
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("must not use pull_request_target" in error for error in errors)


def test_workflow_policy_rejects_missing_pr_quality_gates(tmp_path: Path) -> None:
    write_workflows(
        tmp_path,
        pull_request_workflow=PULL_REQUEST_WORKFLOW.replace(
            "      - run: python3 -m open_postal_codes.pages --output-root out\n"
            "      - run: git diff --check\n",
            "",
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("open_postal_codes.pages --output-root out" in error for error in errors)
    assert any("git diff --check" in error for error in errors)
