"""Check low-cost GitHub workflow safety policies."""

from __future__ import annotations

import re
from pathlib import Path

from tools.repo_checks.common import fail

WORKFLOW_ROOT = Path(".github/workflows")
PULL_REQUEST_WORKFLOW = WORKFLOW_ROOT / "pull-request.yml"
DATA_REFRESH_WORKFLOW = WORKFLOW_ROOT / "data-refresh.yml"

PR_REQUIRED_SNIPPETS = (
    "pull_request:",
    "pytest --cov=open_postal_codes --cov-fail-under=90",
    "ruff check .",
    "ruff format --check .",
    "mypy src tests tools",
    "tools.repo_checks.all_checks",
    "open_postal_codes.pages --output-root out",
    "git diff --check",
)
PR_FORBIDDEN_SNIPPETS = (
    "open_postal_codes.refresh_data",
    "open-postal-codes-refresh-data",
    "geofabrik-pbf",
    ".osm.pbf",
)
DATA_REFRESH_REQUIRED_SNIPPETS = (
    "workflow_dispatch:",
    "publish:",
    "default: false",
    "type: boolean",
    "cancel-in-progress: false",
    "runs-on: ubuntu-24.04",
    "timeout-minutes: 120",
    "github.ref == 'refs/heads/main'",
    "github.event_name == 'schedule'",
    "github.event_name == 'workflow_dispatch' && inputs.publish",
    "PUBLISH_ENABLED",
    "actions/create-github-app-token@v3",
    "DATA_REFRESH_APP_CLIENT_ID",
    "DATA_REFRESH_APP_PRIVATE_KEY",
    "permission-contents: write",
    "permission-pull-requests: write",
    "permission-checks: read",
    "persist-credentials: false",
    "pytest -m unit --cov=open_postal_codes --cov-fail-under=90",
    "ruff check .",
    "ruff format --check .",
    "mypy src tests tools",
    "python3 -u -m open_postal_codes.refresh_data",
    '--report-path "${RUNNER_TEMP}/refresh-report.json"',
    "open_postal_codes.refresh_data",
    "tools.repo_checks.all_checks",
    "open_postal_codes.pages --output-root out",
    "git diff --check",
    "last-known-good fallback",
    "chore(data): refresh post code outputs",
    "gh pr checks",
    "--required --watch --fail-fast",
    "timeout --signal=TERM --kill-after=30s 20m",
    "headRefOid",
    "gh pr merge",
    "--squash",
    "--delete-branch",
    "--match-head-commit",
    "mergedAt",
    "if: always()",
    "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    "retention-days: 14",
)
DATA_REFRESH_FORBIDDEN_SNIPPETS = (
    "GH_TOKEN: ${{ github.token }}",
    "GITHUB_TOKEN: ${{ github.token }}",
    "data(dach): refresh post code outputs",
    'Path(\\"data/public',
    "python3 -m open_postal_codes.refresh_data",
    "actions/cache@",
)
PUBLICATION_STEP_NAMES = (
    "Generate publication token",
    "Resolve GitHub App bot identity",
    "Commit data changes",
    "Open or update data pull request",
    "Wait for required pull request checks",
    "Merge data pull request",
)
ALWAYS_STEP_NAMES = (
    "Ensure diagnostic report exists",
    "Write final refresh summary",
    "Upload refresh diagnostics",
)
ALLOWED_TOP_LEVEL_KEYS = {
    "name",
    "on",
    "permissions",
    "concurrency",
    "jobs",
}


def has_top_level_key(text: str, key: str) -> bool:
    return re.search(rf"(?m)^{re.escape(key)}:\s*(?:$|#)", text) is not None


def job_blocks(text: str) -> dict[str, str]:
    match = re.search(r"(?m)^jobs:\s*$", text)
    if match is None:
        return {}

    jobs_text = text[match.end() :]
    matches = list(re.finditer(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", jobs_text))
    blocks: dict[str, str] = {}
    for index, job_match in enumerate(matches):
        start = job_match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(jobs_text)
        blocks[job_match.group(1)] = jobs_text[start:end]
    return blocks


def validate_workflow_basics(path: Path, text: str, repository_root: Path) -> list[str]:
    errors: list[str] = []
    display_path = path.relative_to(repository_root)

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line or line.startswith((" ", "#")):
            continue
        key_match = re.match(r"^([A-Za-z_-][A-Za-z0-9_-]*):", line)
        if key_match is None:
            errors.append(f"{display_path}:{line_number} has unexpected top-level content")
            continue
        key = key_match.group(1)
        if key not in ALLOWED_TOP_LEVEL_KEYS:
            errors.append(f"{display_path}:{line_number} has unexpected top-level key: {key}")

    if "pull_request_target:" in text:
        errors.append(f"{display_path} must not use pull_request_target")
    for key in ("permissions", "concurrency"):
        if not has_top_level_key(text, key):
            errors.append(f"{display_path} is missing top-level {key}")

    blocks = job_blocks(text)
    if not blocks:
        errors.append(f"{display_path} does not define jobs")
    for job_name, block in blocks.items():
        if "runs-on:" in block and "timeout-minutes:" not in block:
            errors.append(f"{display_path} job {job_name} is missing timeout-minutes")

    return errors


def validate_pull_request_workflow(text: str) -> list[str]:
    errors: list[str] = []

    for snippet in PR_REQUIRED_SNIPPETS:
        if snippet not in text:
            errors.append(f"pull-request workflow is missing required gate: {snippet}")

    for snippet in PR_FORBIDDEN_SNIPPETS:
        if snippet in text:
            errors.append(f"pull-request workflow must not run live PBF refreshes: {snippet}")

    return errors


def validate_data_refresh_workflow(text: str) -> list[str]:
    errors: list[str] = []

    if re.search(r'cron:\s*["\']17 2 \* \* 1["\']', text) is None:
        errors.append("data-refresh workflow must keep the weekly Monday schedule")

    for snippet in DATA_REFRESH_REQUIRED_SNIPPETS:
        if snippet not in text:
            errors.append(
                f"data-refresh workflow is missing required step or permission: {snippet}"
            )

    for snippet in DATA_REFRESH_FORBIDDEN_SNIPPETS:
        if snippet in text:
            errors.append(f"data-refresh workflow must not use: {snippet}")

    if "id-token: write" in text or "pages: write" in text:
        errors.append(
            "data-refresh workflow write permissions must stay scoped to data pull requests"
        )

    publish_expression = re.compile(
        r"PUBLISH_ENABLED:\s*>-\s*"
        r"\$\{\{\s*github\.ref == 'refs/heads/main'\s*&&\s*"
        r"\(github\.event_name == 'schedule'\s*\|\|\s*"
        r"\(github\.event_name == 'workflow_dispatch'\s*&&\s*inputs\.publish\)\)\s*\}\}",
        re.DOTALL,
    )
    if publish_expression.search(text) is None:
        errors.append(
            "data-refresh publication must allow only schedules or opted-in manual runs on main"
        )

    if re.search(r"(?m)^\s+matrix:\s*$", text):
        errors.append("data-refresh workflow must not use a source or country matrix")

    ordered_steps = (
        "Run code preflight checks",
        "Refresh regional Geofabrik data",
        "Validate generated data and package Pages",
    )
    step_positions = [text.find(f"- name: {step_name}") for step_name in ordered_steps]
    if any(position < 0 for position in step_positions) or step_positions != sorted(step_positions):
        errors.append(
            "data-refresh workflow must run code preflight before refresh and data gates after"
        )

    publication_condition = (
        "if: env.PUBLISH_ENABLED == 'true' && steps.changes.outputs.changed == 'true'"
    )
    for step_name in PUBLICATION_STEP_NAMES:
        pattern = (
            rf"(?m)^      - name: {re.escape(step_name)}\n"
            rf"        {re.escape(publication_condition)}$"
        )
        if re.search(pattern, text) is None:
            errors.append(
                f"data-refresh publication step must use the main-only publish gate: {step_name}"
            )

    for step_name in ALWAYS_STEP_NAMES:
        pattern = rf"(?m)^      - name: {re.escape(step_name)}\n        if: always\(\)$"
        if re.search(pattern, text) is None:
            errors.append(f"data-refresh diagnostic step must always run: {step_name}")

    artifact_block = re.search(
        r"(?ms)^      - name: Upload refresh diagnostics\n(?P<block>.*?)(?=^      - name:|\Z)",
        text,
    )
    if artifact_block is not None and any(
        snippet in artifact_block.group("block")
        for snippet in ("geofabrik-pbf", ".osm.pbf", "data/public", "data/regional")
    ):
        errors.append("data-refresh diagnostic artifact must not upload PBF or data outputs")

    return errors


def validate_workflows(repository_root: Path = Path(".")) -> list[str]:
    errors: list[str] = []
    workflow_root = repository_root / WORKFLOW_ROOT
    workflow_paths = sorted(workflow_root.glob("*.yml"))
    if not workflow_paths:
        return [f"missing workflow directory or files: {workflow_root}"]

    workflow_texts: dict[Path, str] = {}
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        workflow_texts[path.relative_to(repository_root)] = text
        errors.extend(validate_workflow_basics(path, text, repository_root))

    pull_request_text = workflow_texts.get(PULL_REQUEST_WORKFLOW)
    if pull_request_text is None:
        errors.append(f"missing workflow: {PULL_REQUEST_WORKFLOW}")
    else:
        errors.extend(validate_pull_request_workflow(pull_request_text))

    data_refresh_text = workflow_texts.get(DATA_REFRESH_WORKFLOW)
    if data_refresh_text is None:
        errors.append(f"missing workflow: {DATA_REFRESH_WORKFLOW}")
    else:
        errors.extend(validate_data_refresh_workflow(data_refresh_text))

    return errors


def main() -> int:
    return fail("workflow-policy-check", validate_workflows())


if __name__ == "__main__":
    raise SystemExit(main())
