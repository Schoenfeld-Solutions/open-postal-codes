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
    "contents: write",
    "pull-requests: write",
    "open_postal_codes.refresh_data",
    "tools.repo_checks.all_checks",
)


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

    if "id-token: write" in text or "pages: write" in text:
        errors.append(
            "data-refresh workflow write permissions must stay scoped to data pull requests"
        )

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
