"""
Lease rollover risk analysis from rent roll data.
"""

from __future__ import annotations

from datetime import date

from .schemas.self_storage import LeaseRecord, RolloverRisk


def compute_rollover_risk(
    leases: list[LeaseRecord],
    as_of: date | None = None,
) -> RolloverRisk:
    """Compute lease rollover risk buckets from rent roll data.

    Args:
        leases:  List of LeaseRecord objects parsed from a rent roll upload.
        as_of:   Reference date for months-remaining calculations.
                 Defaults to date.today().

    Returns:
        RolloverRisk with expiry buckets, concentration, and avg term.
    """
    if as_of is None:
        as_of = date.today()

    # Total rent across all leases (skip None / zero)
    total_rent = sum(
        lease.monthly_rent
        for lease in leases
        if lease.monthly_rent
    )

    # Parse expirations and compute months remaining
    # Only include leases that have a non-None expiration date.
    dated_leases: list[tuple[int, float]] = []  # (months_remaining, monthly_rent)

    for lease in leases:
        if lease.lease_expiration is None:
            continue
        try:
            exp = date.fromisoformat(lease.lease_expiration)
        except (ValueError, TypeError):
            continue

        # Use actual day delta to avoid off-by-one when expiration is mid-month
        months_remaining = (exp - as_of).days // 30
        dated_leases.append((months_remaining, lease.monthly_rent or 0.0))

    def _pct_expiring_within(months: int) -> float:
        if total_rent == 0:
            return 0.0
        expiring_rent = sum(
            rent for mo, rent in dated_leases if mo <= months
        )
        return expiring_rent / total_rent

    pct_12 = _pct_expiring_within(12)
    pct_24 = _pct_expiring_within(24)
    pct_36 = _pct_expiring_within(36)

    # Top-5 tenant concentration (None if fewer than 2 leases)
    top_5_tenants_pct: float | None = None
    all_rents = [lease.monthly_rent for lease in leases if lease.monthly_rent]
    if len(all_rents) >= 2 and total_rent > 0:
        top_5_rents = sorted(all_rents, reverse=True)[:5]
        top_5_tenants_pct = sum(top_5_rents) / total_rent

    # Average remaining term across leases with a parsed expiration
    avg_remaining_term_months: float | None = None
    if dated_leases:
        avg_remaining_term_months = sum(mo for mo, _ in dated_leases) / len(dated_leases)

    return RolloverRisk(
        pct_rent_expiring_12mo=pct_12,
        pct_rent_expiring_24mo=pct_24,
        pct_rent_expiring_36mo=pct_36,
        top_5_tenants_pct=top_5_tenants_pct,
        avg_remaining_term_months=avg_remaining_term_months,
    )
