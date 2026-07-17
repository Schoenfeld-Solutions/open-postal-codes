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
    inputs:
      publish:
        default: false
        type: boolean

permissions:
  contents: read

concurrency:
  group: data-refresh-post-code
  cancel-in-progress: false

jobs:
  refresh:
    runs-on: ubuntu-24.04
    timeout-minutes: 120
    env:
      PUBLISH_ENABLED: >-
        ${{ github.ref == 'refs/heads/main' &&
            (github.event_name == 'schedule' ||
            (github.event_name == 'workflow_dispatch' && inputs.publish)) }}
    steps:
      - uses: actions/create-github-app-token@v3
        id: checkout-token
        with:
          client-id: ${{ vars.DATA_REFRESH_APP_CLIENT_ID }}
          private-key: ${{ secrets.DATA_REFRESH_APP_PRIVATE_KEY }}
          permission-contents: read
      - uses: actions/checkout@v6
        with:
          token: ${{ steps.checkout-token.outputs.token }}
          persist-credentials: false
      - name: Run code preflight checks
        run: |
          python3 -m pytest -m unit --cov=open_postal_codes --cov-fail-under=90
          python3 -m ruff check .
          python3 -m ruff format --check .
          python3 -m mypy src tests tools
      - name: Refresh regional Geofabrik data
        run: |
          python3 -u -m open_postal_codes.refresh_data \
            --report-path "${RUNNER_TEMP}/refresh-report.json"
      - name: Validate generated data and package Pages
        run: |
          python3 -m tools.repo_checks.all_checks
          python3 -m open_postal_codes.pages --output-root out
          git diff --check
      - name: Detect data changes
        id: changes
        run: echo "changed=true" >> "${GITHUB_OUTPUT}"
      - name: Prepare data pull request body
        if: env.PUBLISH_ENABLED == 'true' && steps.changes.outputs.changed == 'true'
        run: echo "last-known-good fallback"
      - name: Generate publication token
        if: env.PUBLISH_ENABLED == 'true' && steps.changes.outputs.changed == 'true'
        uses: actions/create-github-app-token@v3
        id: publication-token
        with:
          client-id: ${{ vars.DATA_REFRESH_APP_CLIENT_ID }}
          private-key: ${{ secrets.DATA_REFRESH_APP_PRIVATE_KEY }}
          permission-contents: write
          permission-pull-requests: write
          permission-checks: read
      - name: Resolve GitHub App bot identity
        if: env.PUBLISH_ENABLED == 'true' && steps.changes.outputs.changed == 'true'
        run: echo identity
      - name: Commit data changes
        if: env.PUBLISH_ENABLED == 'true' && steps.changes.outputs.changed == 'true'
        run: |
          git commit -m "chore(data): refresh post code outputs"
      - name: Open or update data pull request
        if: env.PUBLISH_ENABLED == 'true' && steps.changes.outputs.changed == 'true'
        run: echo open
      - name: Wait for required pull request checks
        if: env.PUBLISH_ENABLED == 'true' && steps.changes.outputs.changed == 'true'
        run: |
          timeout --signal=TERM --kill-after=30s 20m \
            gh pr checks "${{ steps.data-pr.outputs.number }}" \
              --required --watch --fail-fast
          gh pr view --json headRefOid
      - name: Merge data pull request
        if: env.PUBLISH_ENABLED == 'true' && steps.changes.outputs.changed == 'true'
        run: |
          gh pr merge "${{ steps.data-pr.outputs.number }}" --squash --delete-branch \
            --match-head-commit "${{ steps.commit.outputs.head_sha }}"
          gh pr view --json mergedAt
      - name: Ensure diagnostic report exists
        if: always()
        run: echo report
      - name: Write final refresh summary
        if: always()
        run: echo summary
      - name: Upload refresh diagnostics
        if: always()
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          path: ${{ runner.temp }}/refresh-report.json
          retention-days: 14
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


def test_workflow_policy_rejects_unindented_script_content(tmp_path: Path) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW + "import sys\n",
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("unexpected top-level content" in error for error in errors)


def test_workflow_policy_rejects_default_token_for_data_pull_requests(
    tmp_path: Path,
) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=(
            DATA_REFRESH_WORKFLOW
            + "      - run: echo unsafe\n"
            + "        env:\n"
            + "          GH_TOKEN: ${{ github.token }}\n"
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("GH_TOKEN: ${{ github.token }}" in error for error in errors)


def test_workflow_policy_rejects_missing_automated_merge_guardrails(
    tmp_path: Path,
) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW.replace(
            "gh pr merge", "gh pr no-merge"
        ).replace("--match-head-commit", "--unchecked-head"),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("gh pr merge" in error for error in errors)
    assert any("--match-head-commit" in error for error in errors)


def test_workflow_policy_rejects_invalid_data_refresh_commit_title(
    tmp_path: Path,
) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW.replace(
            "chore(data): refresh post code outputs",
            "data(dach): refresh post code outputs",
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("data(dach): refresh post code outputs" in error for error in errors)


def test_workflow_policy_rejects_escaped_refresh_record_count_commands(
    tmp_path: Path,
) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW
        + "      - run: echo \"records_de=$(python3 -c 'from pathlib import Path; "
        + 'print(Path(\\"data/public/v1/de/post_code.csv\\"))\')"\n',
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any('Path(\\"data/public' in error for error in errors)


def test_workflow_policy_rejects_buffered_data_refresh_invocation(
    tmp_path: Path,
) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW.replace(
            "python3 -u -m open_postal_codes.refresh_data",
            "python3 -m open_postal_codes.refresh_data",
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("python3 -u -m open_postal_codes.refresh_data" in error for error in errors)
    assert any("python3 -m open_postal_codes.refresh_data" in error for error in errors)


def test_workflow_policy_rejects_cancelled_or_unbounded_refresh_runs(
    tmp_path: Path,
) -> None:
    workflow = DATA_REFRESH_WORKFLOW.replace(
        "  cancel-in-progress: false", "  cancel-in-progress: true"
    ).replace("    timeout-minutes: 120", "    timeout-minutes: 240")
    write_workflows(tmp_path, data_refresh_workflow=workflow)

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("cancel-in-progress: false" in error for error in errors)
    assert any("timeout-minutes: 120" in error for error in errors)


def test_workflow_policy_rejects_publication_without_main_only_gate(
    tmp_path: Path,
) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW.replace(
            "github.ref == 'refs/heads/main'", "github.ref != ''"
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("github.ref == 'refs/heads/main'" in error for error in errors)


def test_workflow_policy_rejects_ungated_publication_step(tmp_path: Path) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW.replace(
            "      - name: Commit data changes\n"
            "        if: env.PUBLISH_ENABLED == 'true' && "
            "steps.changes.outputs.changed == 'true'\n",
            "      - name: Commit data changes\n",
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("main-only publish gate: Commit data changes" in error for error in errors)


def test_workflow_policy_rejects_non_diagnostic_artifacts(tmp_path: Path) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW.replace(
            "          path: ${{ runner.temp }}/refresh-report.json",
            "          path: ${{ runner.temp }}/geofabrik-pbf",
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("must not upload PBF or data outputs" in error for error in errors)


def test_workflow_policy_rejects_matrix_and_manual_cache(tmp_path: Path) -> None:
    workflow = DATA_REFRESH_WORKFLOW.replace(
        "    steps:\n",
        "    strategy:\n      matrix:\n        country: [de, at, ch]\n"
        "    steps:\n      - uses: actions/cache@v4\n",
        1,
    )
    write_workflows(tmp_path, data_refresh_workflow=workflow)

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("must not use a source or country matrix" in error for error in errors)
    assert any("actions/cache@" in error for error in errors)


def test_workflow_policy_rejects_diagnostic_step_without_always(tmp_path: Path) -> None:
    write_workflows(
        tmp_path,
        data_refresh_workflow=DATA_REFRESH_WORKFLOW.replace(
            "      - name: Write final refresh summary\n        if: always()\n",
            "      - name: Write final refresh summary\n",
        ),
    )

    errors = workflow_policy_check.validate_workflows(tmp_path)

    assert any("must always run: Write final refresh summary" in error for error in errors)
