"""Read-only discovery of EC2 resources from a local Terraform state file."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class TerraformDiscoveryError(RuntimeError):
    """Raised when Terraform state cannot be read safely."""


@dataclass(frozen=True)
class TerraformResource:
    address: str
    instance_id: str
    instance_type: str


def discover_ec2_resources(terraform_dir: Path) -> list[TerraformResource]:
    """Read resources using ``terraform show -json``; never run apply/plan."""
    if not (terraform_dir / ".terraform" / "terraform.tfstate").exists() and not (
        terraform_dir / "terraform.tfstate"
    ).exists():
        return []

    try:
        result = subprocess.run(
            ["terraform", "show", "-json"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TerraformDiscoveryError("Unable to read Terraform state") from exc
    if result.returncode != 0:
        raise TerraformDiscoveryError("terraform show -json failed")

    try:
        state = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TerraformDiscoveryError("Terraform returned invalid JSON state") from exc

    resources: list[TerraformResource] = []
    for resource in _walk_resources(state.get("values", {}).get("root_module", {})):
        values = resource.get("values", {})
        instance_id = values.get("id")
        instance_type = values.get("instance_type")
        if resource.get("type") == "aws_instance" and instance_id and instance_type:
            resources.append(
                TerraformResource(
                    address=resource["address"],
                    instance_id=instance_id,
                    instance_type=instance_type,
                )
            )
    return resources


def _walk_resources(module: dict) -> list[dict]:
    found = list(module.get("resources", []))
    for child in module.get("child_modules", []):
        found.extend(_walk_resources(child))
    return found
