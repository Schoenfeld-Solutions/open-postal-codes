"""Run all deterministic repository checks."""

from __future__ import annotations

from collections.abc import Callable

from tools.repo_checks import (
    adr_check,
    boundary_truth_check,
    changelog_check,
    language_policy_check,
    license_credit_check,
    module_size_check,
    pages_artifact_check,
    pages_contract_check,
    plans_check,
    project_structure_check,
    public_data_quality_check,
    readme_check,
    reference_policy_check,
    workflow_policy_check,
)

CHECKS: tuple[Callable[[], int], ...] = (
    project_structure_check.main,
    adr_check.main,
    plans_check.main,
    readme_check.main,
    changelog_check.main,
    language_policy_check.main,
    license_credit_check.main,
    pages_contract_check.main,
    pages_artifact_check.main,
    public_data_quality_check.main,
    workflow_policy_check.main,
    boundary_truth_check.main,
    module_size_check.main,
    reference_policy_check.main,
)


def main() -> int:
    status = 0
    for check in CHECKS:
        status = max(status, check())
    return status


if __name__ == "__main__":
    raise SystemExit(main())
