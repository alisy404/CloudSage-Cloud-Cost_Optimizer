from __future__ import annotations

import pytest

from app.terraform.workflow import (
    PlanSummary,
    TerraformWorkflowError,
    require_apply_enabled,
    validate_plan,
)


def test_valid_plan_has_only_intended_change() -> None:
    validate_plan(PlanSummary(0, 1, 0, ("aws_instance.api_server",)), "aws_instance.api_server")


@pytest.mark.parametrize(
    "summary, message",
    [
        (PlanSummary(0, 1, 1, ("aws_instance.api_server",)), "destroy"),
        (PlanSummary(0, 1, 0, ("aws_instance.other",)), "unrelated"),
        (PlanSummary(0, 0, 0, ()), "no intended change"),
    ],
)
def test_unsafe_plan_is_blocked(summary, message) -> None:
    with pytest.raises(TerraformWorkflowError, match=message):
        validate_plan(summary, "aws_instance.api_server")


def test_apply_is_disabled_by_default() -> None:
    with pytest.raises(TerraformWorkflowError, match="disabled"):
        require_apply_enabled(False)
