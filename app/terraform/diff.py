"""Deterministic, review-only Terraform diffs.

This module never writes Terraform files and never executes Terraform.
"""
from __future__ import annotations

from dataclasses import dataclass


class TerraformDiffError(ValueError):
    """Raised when a safe, unambiguous diff cannot be generated."""


@dataclass(frozen=True)
class TerraformDiff:
    instance_id: str
    resource_address: str
    current_type: str
    proposed_type: str
    unified_diff: str


def generate_instance_type_diff(
    *,
    instance_id: str,
    current_type: str,
    proposed_type: str,
    resource_address: str | None,
    approved: bool,
) -> TerraformDiff:
    """Create an exact EC2 instance-type diff after recommendation approval."""
    if not approved:
        raise TerraformDiffError("Terraform diff requires an approved recommendation")
    if not resource_address:
        raise TerraformDiffError("Terraform mapping is missing or ambiguous")
    if current_type == proposed_type:
        raise TerraformDiffError("Terraform diff requires a changed instance type")
    if not proposed_type:
        raise TerraformDiffError("Terraform proposed instance type is missing")

    diff = (
        f"--- {resource_address}\n"
        f"+++ {resource_address} (proposed)\n"
        f"@@ instance_type @@\n"
        f"-instance_type = \"{current_type}\"\n"
        f"+instance_type = \"{proposed_type}\"\n"
    )
    return TerraformDiff(
        instance_id=instance_id,
        resource_address=resource_address,
        current_type=current_type,
        proposed_type=proposed_type,
        unified_diff=diff,
    )
