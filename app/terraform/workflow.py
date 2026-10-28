"""Stage 8-10 Terraform safety policy; no apply is enabled by default."""
from __future__ import annotations

from dataclasses import dataclass


class TerraformWorkflowError(ValueError):
    """Raised when a Terraform workflow transition is unsafe."""


@dataclass(frozen=True)
class PlanSummary:
    add: int
    change: int
    destroy: int
    resource_addresses: tuple[str, ...]


def validate_plan(summary: PlanSummary, intended_address: str) -> None:
    if summary.destroy:
        raise TerraformWorkflowError("Terraform plan contains destroy actions")
    if any(address != intended_address for address in summary.resource_addresses):
        raise TerraformWorkflowError("Terraform plan contains unrelated resources")
    if summary.add + summary.change == 0:
        raise TerraformWorkflowError("Terraform plan contains no intended change")


def require_apply_enabled(enabled: bool) -> None:
    if not enabled:
        raise TerraformWorkflowError("Terraform apply is disabled by safety policy")
