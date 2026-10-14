"""Deterministic EC2 pricing catalog and lookup functions.

Prices reflect AWS standard Linux On-Demand rates in USD.
Monthly costs are computed using the industry standard 730 hours/month (365 * 24 / 12).
Annual costs are computed using 8,760 hours/year (365 * 24).

The catalog covers popular general purpose (t2, t3, t4g, m5, m6i), compute (c5, c6i),
and memory (r5, r6i) families across major regions. If a region is not explicitly
listed, standard fallback pricing is applied.
"""
from __future__ import annotations

from app.models import InstancePricing

HOURS_PER_MONTH = 730.0
HOURS_PER_YEAR = 8760.0

# Base on-demand hourly rates in USD (Linux / Unix, shared tenancy).
# Structure: instance_type -> { "vcpu": int, "memory_gib": float, "rates": { region: float, "default": float } }
_PRICING_CATALOG: dict[str, dict] = {
    # ── T2 Family (Burstable, previous gen) ──
    "t2.nano": {
        "vcpu": 1,
        "memory_gib": 0.5,
        "rates": {"us-east-1": 0.0058, "us-west-2": 0.0058, "ap-south-1": 0.0063, "default": 0.0058},
    },
    "t2.micro": {
        "vcpu": 1,
        "memory_gib": 1.0,
        "rates": {"us-east-1": 0.0116, "us-west-2": 0.0116, "ap-south-1": 0.0126, "default": 0.0116},
    },
    "t2.small": {
        "vcpu": 1,
        "memory_gib": 2.0,
        "rates": {"us-east-1": 0.023, "us-west-2": 0.023, "ap-south-1": 0.0252, "default": 0.023},
    },
    "t2.medium": {
        "vcpu": 2,
        "memory_gib": 4.0,
        "rates": {"us-east-1": 0.0464, "us-west-2": 0.0464, "ap-south-1": 0.0504, "default": 0.0464},
    },
    "t2.large": {
        "vcpu": 2,
        "memory_gib": 8.0,
        "rates": {"us-east-1": 0.0928, "us-west-2": 0.0928, "ap-south-1": 0.1008, "default": 0.0928},
    },
    "t2.xlarge": {
        "vcpu": 4,
        "memory_gib": 16.0,
        "rates": {"us-east-1": 0.1856, "us-west-2": 0.1856, "ap-south-1": 0.2016, "default": 0.1856},
    },
    # ── T3 Family (Burstable, current gen x86) ──
    "t3.nano": {
        "vcpu": 2,
        "memory_gib": 0.5,
        "rates": {"us-east-1": 0.0052, "us-west-2": 0.0052, "ap-south-1": 0.0056, "default": 0.0052},
    },
    "t3.micro": {
        "vcpu": 2,
        "memory_gib": 1.0,
        "rates": {"us-east-1": 0.0104, "us-west-2": 0.0104, "ap-south-1": 0.0112, "default": 0.0104},
    },
    "t3.small": {
        "vcpu": 2,
        "memory_gib": 2.0,
        "rates": {"us-east-1": 0.0208, "us-west-2": 0.0208, "ap-south-1": 0.0224, "default": 0.0208},
    },
    "t3.medium": {
        "vcpu": 2,
        "memory_gib": 4.0,
        "rates": {"us-east-1": 0.0416, "us-west-2": 0.0416, "ap-south-1": 0.0448, "default": 0.0416},
    },
    "t3.large": {
        "vcpu": 2,
        "memory_gib": 8.0,
        "rates": {"us-east-1": 0.0832, "us-west-2": 0.0832, "ap-south-1": 0.0896, "default": 0.0832},
    },
    "t3.xlarge": {
        "vcpu": 4,
        "memory_gib": 16.0,
        "rates": {"us-east-1": 0.1664, "us-west-2": 0.1664, "ap-south-1": 0.1792, "default": 0.1664},
    },
    "t3.2xlarge": {
        "vcpu": 8,
        "memory_gib": 32.0,
        "rates": {"us-east-1": 0.3328, "us-west-2": 0.3328, "ap-south-1": 0.3584, "default": 0.3328},
    },
    # ── T4g Family (Burstable, Graviton2 ARM) ──
    "t4g.nano": {
        "vcpu": 2,
        "memory_gib": 0.5,
        "rates": {"us-east-1": 0.0042, "us-west-2": 0.0042, "ap-south-1": 0.0045, "default": 0.0042},
    },
    "t4g.micro": {
        "vcpu": 2,
        "memory_gib": 1.0,
        "rates": {"us-east-1": 0.0084, "us-west-2": 0.0084, "ap-south-1": 0.0090, "default": 0.0084},
    },
    "t4g.small": {
        "vcpu": 2,
        "memory_gib": 2.0,
        "rates": {"us-east-1": 0.0168, "us-west-2": 0.0168, "ap-south-1": 0.0180, "default": 0.0168},
    },
    "t4g.medium": {
        "vcpu": 2,
        "memory_gib": 4.0,
        "rates": {"us-east-1": 0.0336, "us-west-2": 0.0336, "ap-south-1": 0.0360, "default": 0.0336},
    },
    "t4g.large": {
        "vcpu": 2,
        "memory_gib": 8.0,
        "rates": {"us-east-1": 0.0672, "us-west-2": 0.0672, "ap-south-1": 0.0720, "default": 0.0672},
    },
    "t4g.xlarge": {
        "vcpu": 4,
        "memory_gib": 16.0,
        "rates": {"us-east-1": 0.1344, "us-west-2": 0.1344, "ap-south-1": 0.1440, "default": 0.1344},
    },
    # ── M5 Family (General Purpose x86) ──
    "m5.large": {
        "vcpu": 2,
        "memory_gib": 8.0,
        "rates": {"us-east-1": 0.096, "us-west-2": 0.096, "ap-south-1": 0.101, "default": 0.096},
    },
    "m5.xlarge": {
        "vcpu": 4,
        "memory_gib": 16.0,
        "rates": {"us-east-1": 0.192, "us-west-2": 0.192, "ap-south-1": 0.202, "default": 0.192},
    },
    "m5.2xlarge": {
        "vcpu": 8,
        "memory_gib": 32.0,
        "rates": {"us-east-1": 0.384, "us-west-2": 0.384, "ap-south-1": 0.404, "default": 0.384},
    },
    # ── M6i Family (General Purpose Ice Lake x86) ──
    "m6i.large": {
        "vcpu": 2,
        "memory_gib": 8.0,
        "rates": {"us-east-1": 0.096, "us-west-2": 0.096, "ap-south-1": 0.101, "default": 0.096},
    },
    "m6i.xlarge": {
        "vcpu": 4,
        "memory_gib": 16.0,
        "rates": {"us-east-1": 0.192, "us-west-2": 0.192, "ap-south-1": 0.202, "default": 0.192},
    },
    # ── C5 Family (Compute Optimized) ──
    "c5.large": {
        "vcpu": 2,
        "memory_gib": 4.0,
        "rates": {"us-east-1": 0.085, "us-west-2": 0.085, "ap-south-1": 0.093, "default": 0.085},
    },
    "c5.xlarge": {
        "vcpu": 4,
        "memory_gib": 8.0,
        "rates": {"us-east-1": 0.170, "us-west-2": 0.170, "ap-south-1": 0.186, "default": 0.170},
    },
    # ── R5 Family (Memory Optimized) ──
    "r5.large": {
        "vcpu": 2,
        "memory_gib": 16.0,
        "rates": {"us-east-1": 0.126, "us-west-2": 0.126, "ap-south-1": 0.138, "default": 0.126},
    },
    "r5.xlarge": {
        "vcpu": 4,
        "memory_gib": 32.0,
        "rates": {"us-east-1": 0.252, "us-west-2": 0.252, "ap-south-1": 0.276, "default": 0.252},
    },
}

# Downsizing family hierarchy chains (from larger to smaller).
_DOWNSIZING_HIERARCHIES: list[list[str]] = [
    ["t2.2xlarge", "t2.xlarge", "t2.large", "t2.medium", "t2.small", "t2.micro", "t2.nano"],
    ["t3.2xlarge", "t3.xlarge", "t3.large", "t3.medium", "t3.small", "t3.micro", "t3.nano"],
    ["t4g.2xlarge", "t4g.xlarge", "t4g.large", "t4g.medium", "t4g.small", "t4g.micro", "t4g.nano"],
    ["m5.2xlarge", "m5.xlarge", "m5.large", "t3.xlarge", "t3.large"],
    ["m6i.2xlarge", "m6i.xlarge", "m6i.large", "t3.xlarge", "t3.large"],
    ["c5.2xlarge", "c5.xlarge", "c5.large", "t3.large", "t3.medium"],
    ["r5.2xlarge", "r5.xlarge", "r5.large", "t3.xlarge", "t3.large"],
]


def get_instance_pricing(instance_type: str, region: str = "us-east-1") -> InstancePricing | None:
    """Look up deterministic on-demand pricing for an EC2 instance type."""
    entry = _PRICING_CATALOG.get(instance_type)
    if entry is None:
        return None

    rates = entry["rates"]
    hourly = rates.get(region, rates.get("default", 0.0))
    monthly = round(hourly * HOURS_PER_MONTH, 4)

    return InstancePricing(
        instance_type=instance_type,
        region=region,
        hourly_rate_usd=hourly,
        monthly_rate_usd=monthly,
        vcpu=entry["vcpu"],
        memory_gib=entry["memory_gib"],
        currency="USD",
        pricing_source="AWS On-Demand Catalog",
    )


def get_downsizing_targets(current_type: str) -> list[str]:
    """Return an ordered list of candidate smaller instance types within the family/profile."""
    for chain in _DOWNSIZING_HIERARCHIES:
        if current_type in chain:
            idx = chain.index(current_type)
            # Return types that come after in the chain (i.e. smaller)
            return [t for t in chain[idx + 1 :] if t in _PRICING_CATALOG]
    return []
