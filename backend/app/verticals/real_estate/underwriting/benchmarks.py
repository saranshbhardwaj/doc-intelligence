"""Self-storage underwriting benchmark constants.

Values sourced from CBRE Self Storage Almanac and SSA industry data.
Benchmarks represent national averages; regional variation should be
applied by the analyst via the input panel override.
"""
from __future__ import annotations
from typing import Optional

BENCHMARKS: dict[str, dict[str, dict[str, float]]] = {
    "self_storage": {
        # Per rentable square foot
        "repairs_per_sqft":   {"floor": 0.10, "typical": 0.12},
        "insurance_per_sqft": {"floor": 0.35, "typical": 0.45},
        "utilities_per_sqft": {"floor": 0.25, "typical": 0.35},
        # As fraction of EGI
        "marketing_pct_egi":  {"floor": 0.03, "typical": 0.04},
        "mgmt_fee_pct_egi":   {"floor": 0.05, "typical": 0.06},
        "bank_fees_pct_egi":  {"floor": 0.015, "typical": 0.0175},
    },
}


def get_expense_floors(
    asset_type: str,
    rentable_sqft: Optional[float] = None,
    egi: Optional[float] = None,
) -> dict[str, float]:
    """Return computed expense floor values for an asset type.

    Keys map to SelfStorageInputs operational field names.
    Only includes floors for which the required size/egi inputs are present.
    Returns empty dict for unknown asset types.
    """
    b = BENCHMARKS.get(asset_type)
    if not b:
        return {}

    floors: dict[str, float] = {}

    if rentable_sqft:
        floors["repairs_maintenance_annual"] = rentable_sqft * b["repairs_per_sqft"]["floor"]
        floors["insurance_annual"] = rentable_sqft * b["insurance_per_sqft"]["floor"]
        floors["utilities_annual"] = rentable_sqft * b["utilities_per_sqft"]["floor"]

    if egi:
        floors["marketing_annual"] = egi * b["marketing_pct_egi"]["floor"]

    return floors
