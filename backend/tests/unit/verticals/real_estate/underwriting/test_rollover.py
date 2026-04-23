"""Unit tests for lease rollover risk calculation."""
from datetime import date
import pytest
from app.verticals.real_estate.underwriting.rollover import compute_rollover_risk
from app.verticals.real_estate.underwriting.schemas.self_storage import LeaseRecord


AS_OF = date(2025, 6, 1)  # Fixed for determinism


class TestRolloverHappyPath:
    """Happy path: 3 leases expiring at different times."""

    def test_correct_bucket_percentages(self):
        """3 leases at 6m, 18m, 30m → correct bucket percentages."""
        leases = [
            LeaseRecord(unit_id="A1", tenant_name="Tenant A", monthly_rent=1000, lease_expiration="2025-12-01"),  # 6 months
            LeaseRecord(unit_id="B1", tenant_name="Tenant B", monthly_rent=1500, lease_expiration="2026-12-01"),  # 18 months
            LeaseRecord(unit_id="C1", tenant_name="Tenant C", monthly_rent=500, lease_expiration="2027-12-01"),  # 30 months
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        total_rent = 3000  # 1000 + 1500 + 500
        assert risk.pct_rent_expiring_12mo == pytest.approx(1000 / total_rent)
        assert risk.pct_rent_expiring_24mo == pytest.approx((1000 + 1500) / total_rent)
        assert risk.pct_rent_expiring_36mo == pytest.approx(1.0)

    def test_avg_remaining_term_months(self):
        """Average remaining term computed correctly."""
        leases = [
            LeaseRecord(unit_id="A1", tenant_name="A", monthly_rent=1000, lease_expiration="2025-12-01"),  # 6 months
            LeaseRecord(unit_id="B1", tenant_name="B", monthly_rent=1000, lease_expiration="2026-06-01"),  # 12 months
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        # Avg = (6 + 12) / 2 = 9 months
        assert risk.avg_remaining_term_months == pytest.approx(9.0)


class TestRolloverEdgeCases:
    """Edge cases: None dates, expired leases, top-5 edge."""

    def test_all_leases_no_expiration_dates(self):
        """All leases have lease_expiration=None → all percentages = 0.0."""
        leases = [
            LeaseRecord(unit_id="A1", tenant_name="A", monthly_rent=1000, lease_expiration=None),
            LeaseRecord(unit_id="B1", tenant_name="B", monthly_rent=1500, lease_expiration=None),
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        assert risk.pct_rent_expiring_12mo == 0.0
        assert risk.pct_rent_expiring_24mo == 0.0
        assert risk.pct_rent_expiring_36mo == 0.0

    def test_already_expired_leases_count_to_all_buckets(self):
        """Already-expired lease counts toward all buckets (negative months ≤ N)."""
        leases = [
            LeaseRecord(unit_id="A1", tenant_name="A", monthly_rent=1000, lease_expiration="2025-01-01"),  # Already expired (-5 months)
            LeaseRecord(unit_id="B1", tenant_name="B", monthly_rent=1000, lease_expiration="2025-12-01"),  # 6 months
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        # Expired lease counts in all buckets
        # Expected: (1000 + 1000) / 2000 = 1.0 for 12mo (both count)
        assert risk.pct_rent_expiring_12mo == pytest.approx(1.0)
        assert risk.pct_rent_expiring_24mo == pytest.approx(1.0)
        assert risk.pct_rent_expiring_36mo == pytest.approx(1.0)

    def test_top_5_tenants_exactly_5_leases(self):
        """Exactly 5 leases → top_5_tenants_pct = 1.0."""
        leases = [
            LeaseRecord(unit_id=f"U{i}", tenant_name=f"T{i}", monthly_rent=1000, lease_expiration="2026-01-01")
            for i in range(5)
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        assert risk.top_5_tenants_pct == pytest.approx(1.0)

    def test_top_5_tenants_10_leases(self):
        """10 equal leases → top 5 = 50%."""
        leases = [
            LeaseRecord(unit_id=f"U{i}", tenant_name=f"T{i}", monthly_rent=1000, lease_expiration="2026-01-01")
            for i in range(10)
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        # Top 5 / 10 = 50%
        assert risk.top_5_tenants_pct == pytest.approx(0.5)

    def test_top_5_tenants_single_lease(self):
        """Single lease → top_5_tenants_pct = None (needs >= 2 rents)."""
        leases = [
            LeaseRecord(unit_id="A1", tenant_name="A", monthly_rent=1000, lease_expiration="2026-01-01"),
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        # Only 1 lease → None
        assert risk.top_5_tenants_pct is None

    def test_top_5_tenants_two_leases(self):
        """Two leases (min for top-5 computation)."""
        leases = [
            LeaseRecord(unit_id="A1", tenant_name="A", monthly_rent=2000, lease_expiration="2026-01-01"),
            LeaseRecord(unit_id="B1", tenant_name="B", monthly_rent=1000, lease_expiration="2026-01-01"),
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        # Top 5 = top 2 (only 2 exist) = 3000 / 3000 = 1.0
        assert risk.top_5_tenants_pct == pytest.approx(1.0)

    def test_unparseable_expiration_date_ignored(self):
        """Unparseable lease_expiration string → lease excluded silently."""
        leases = [
            LeaseRecord(unit_id="A1", tenant_name="A", monthly_rent=1000, lease_expiration="invalid-date"),
            LeaseRecord(unit_id="B1", tenant_name="B", monthly_rent=1000, lease_expiration="2026-01-01"),
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        # Only the valid lease (B1) counts
        assert risk.pct_rent_expiring_12mo > 0
        # avg_remaining_term should be for B1 only (~7 months)
        assert risk.avg_remaining_term_months is not None

    def test_no_leases(self):
        """Empty lease list → all zeros."""
        leases = []

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        assert risk.pct_rent_expiring_12mo == 0.0
        assert risk.pct_rent_expiring_24mo == 0.0
        assert risk.pct_rent_expiring_36mo == 0.0
        assert risk.avg_remaining_term_months is None or risk.avg_remaining_term_months == 0.0

    def test_no_monthly_rent_recorded(self):
        """Lease with monthly_rent=0 or missing → excluded from totals."""
        leases = [
            LeaseRecord(unit_id="A1", tenant_name="A", monthly_rent=1000, lease_expiration="2025-12-01"),
            LeaseRecord(unit_id="B1", tenant_name="B", monthly_rent=0, lease_expiration="2025-12-01"),  # Zero rent
        ]

        risk = compute_rollover_risk(leases, as_of=AS_OF)

        # Only A1 counts
        assert risk.pct_rent_expiring_12mo == pytest.approx(1.0)
