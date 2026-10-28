from __future__ import annotations

import pytest

from app.terraform.diff import TerraformDiffError, generate_instance_type_diff


def test_generates_exact_review_diff_for_approved_mapping() -> None:
    result = generate_instance_type_diff(
        instance_id="i-test",
        current_type="t3.large",
        proposed_type="t3.medium",
        resource_address="aws_instance.api_server",
        approved=True,
    )

    assert result.unified_diff == (
        "--- aws_instance.api_server\n"
        "+++ aws_instance.api_server (proposed)\n"
        "@@ instance_type @@\n"
        "-instance_type = \"t3.large\"\n"
        "+instance_type = \"t3.medium\"\n"
    )


@pytest.mark.parametrize(
    ("approved", "resource_address", "expected"),
    [
        (False, "aws_instance.api_server", "approved"),
        (True, None, "ambiguous"),
    ],
)
def test_blocks_unsafe_or_ambiguous_diff(approved, resource_address, expected) -> None:
    with pytest.raises(TerraformDiffError, match=expected):
        generate_instance_type_diff(
            instance_id="i-test",
            current_type="t3.large",
            proposed_type="t3.medium",
            resource_address=resource_address,
            approved=approved,
        )
