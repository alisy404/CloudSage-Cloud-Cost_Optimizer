import json
from pathlib import Path
from unittest.mock import patch

from app.terraform.discovery import discover_ec2_resources


def test_discovery_reads_aws_instance_from_terraform_show(tmp_path: Path) -> None:
    (tmp_path / "terraform.tfstate").write_text("placeholder")
    state = {
        "values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_instance.cloudsage_test",
                        "type": "aws_instance",
                        "values": {"id": "i-real", "instance_type": "t3.micro"},
                    }
                ]
            }
        }
    }
    completed = type("Completed", (), {"returncode": 0, "stdout": json.dumps(state)})()
    with patch("app.terraform.discovery.subprocess.run", return_value=completed):
        result = discover_ec2_resources(tmp_path)

    assert result[0].address == "aws_instance.cloudsage_test"
    assert result[0].instance_id == "i-real"
    assert result[0].instance_type == "t3.micro"


def test_discovery_returns_empty_without_state(tmp_path: Path) -> None:
    assert discover_ec2_resources(tmp_path) == []
