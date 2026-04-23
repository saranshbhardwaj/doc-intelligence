"""Unit tests for cross-document discrepancy detection."""
import pytest
from app.verticals.real_estate.underwriting.extraction.discrepancy import detect_discrepancies


class TestDiscrepancyNoIssues:
    """No discrepancies: matching data across all docs."""

    def test_no_discrepancies_matching_data(self):
        """Matching OM + rent_roll + t12 → empty list."""
        om_data = {
            "num_units": 150,
            "occupancy_pct": 0.92,
            "gross_potential_rent_annual": 600_000,
            "rentable_sqft": 75_000,
            "opex_pct": 0.38,
        }
        rent_roll_data = {
            "summary": {
                "total_units": 150,
                "occupancy_pct": 0.92,
                "annual_gross_potential_rent": 600_000,
                "total_sqft": 75_000,
            }
        }
        t12_data = {
            "summary": {
                "opex_ratio": 0.38,
            }
        }

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert discrepancies == []


class TestDiscrepancyRule1UnitCount:
    """Rule 1: Unit count must match exactly."""

    def test_unit_count_mismatch_triggers_error(self):
        """OM=150, rent_roll=145 → error severity discrepancy."""
        om_data = {"num_units": 150}
        rent_roll_data = {"summary": {"total_units": 145}}
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "num_units"
        assert discrepancies[0]["severity"] == "error"

    def test_unit_count_matching_no_error(self):
        """OM=150, rent_roll=150 → no error."""
        om_data = {"num_units": 150}
        rent_roll_data = {"summary": {"total_units": 150}}
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 0


class TestDiscrepancyRule2Occupancy:
    """Rule 2: Occupancy delta > 2pp triggers warning."""

    def test_occupancy_delta_4pp_triggers_warning(self):
        """OM=0.93, rent_roll=0.89 → warning (delta=4pp > 2pp)."""
        om_data = {"occupancy_pct": 0.93}
        rent_roll_data = {"summary": {"occupancy_pct": 0.89}}
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "occupancy_pct"
        assert discrepancies[0]["severity"] == "warning"

    def test_occupancy_delta_1pp_no_warning(self):
        """OM=0.93, rent_roll=0.92 → no warning (delta=1pp < 2pp)."""
        om_data = {"occupancy_pct": 0.93}
        rent_roll_data = {"summary": {"occupancy_pct": 0.92}}
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 0

    def test_occupancy_delta_2pp_boundary_no_warning(self):
        """Delta exactly 2pp → no warning (threshold is > 2pp, not >= 2pp)."""
        om_data = {"occupancy_pct": 0.95}
        rent_roll_data = {"summary": {"occupancy_pct": 0.93}}
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 0


class TestDiscrepancyRule3GPR:
    """Rule 3: GPR delta > 3% relative triggers warning."""

    def test_gpr_delta_16pct_triggers_warning(self):
        """OM=600_000, rent_roll=500_000 → warning (delta=16.7%)."""
        om_data = {"gross_potential_rent_annual": 600_000}
        rent_roll_data = {"summary": {"annual_gross_potential_rent": 500_000}}
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "gross_potential_rent_annual"

    def test_gpr_delta_3pct_boundary_triggers_warning(self):
        """Delta exactly 3% → warning (threshold is >= 3%)."""
        om_data = {"gross_potential_rent_annual": 600_000}
        rent_roll_data = {"summary": {"annual_gross_potential_rent": 582_000}}  # 3% lower
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "gross_potential_rent_annual"

    def test_gpr_delta_2pct_no_warning(self):
        """Delta 2% < 3% → no warning."""
        om_data = {"gross_potential_rent_annual": 600_000}
        rent_roll_data = {"summary": {"annual_gross_potential_rent": 588_000}}  # 2% lower
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 0


class TestDiscrepancyRule4OpEx:
    """Rule 4: OpEx ratio delta > 200bps triggers warning."""

    def test_opex_delta_300bps_triggers_warning(self):
        """OM=0.40, t12=0.37 → warning (delta=300bps)."""
        om_data = {"opex_pct": 0.40}
        rent_roll_data = {}
        t12_data = {"summary": {"opex_ratio": 0.37}}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "opex_ratio"

    def test_opex_delta_200bps_boundary_triggers_warning(self):
        """Delta exactly 200bps → warning (threshold is >= 200bps)."""
        om_data = {"opex_pct": 0.38}
        rent_roll_data = {}
        t12_data = {"summary": {"opex_ratio": 0.36}}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "opex_ratio"

    def test_opex_delta_100bps_no_warning(self):
        """Delta 100bps < 200bps → no warning."""
        om_data = {"opex_pct": 0.39}
        rent_roll_data = {}
        t12_data = {"summary": {"opex_ratio": 0.38}}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 0


class TestDiscrepancyRule5SqFt:
    """Rule 5: SqFt delta > 1% relative triggers info-level discrepancy."""

    def test_sqft_delta_5pct_triggers_info(self):
        """OM=75_000, rent_roll=71_250 → info level (delta=5%)."""
        om_data = {"rentable_sqft": 75_000}
        rent_roll_data = {"summary": {"total_sqft": 71_250}}
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "rentable_sqft"
        assert discrepancies[0]["severity"] == "info"


class TestDiscrepancyRule6UnitMix:
    """Rule 6: rent-roll unit mix should align with OM if both are present."""

    def test_unit_mix_bucket_count_mismatch_triggers_warning(self):
        om_data = {
            "unit_mix": [
                {"section": "NON-CLIMATE", "unit_type": "10 x 10", "size": "10 x 10", "num_units": 64}
            ]
        }
        rent_roll_data = {
            "unit_mix": [
                {"section": "NON-CLIMATE", "unit_type": "10 x 10", "size": "10 x 10", "num_units": 60}
            ]
        }

        discrepancies = detect_discrepancies(om_data, rent_roll_data, {})

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "unit_mix"
        assert discrepancies[0]["severity"] == "warning"

    def test_unit_mix_missing_bucket_triggers_warning(self):
        om_data = {
            "unit_mix": [
                {"section": "NON-CLIMATE", "unit_type": "10 x 10", "size": "10 x 10", "num_units": 64}
            ]
        }
        rent_roll_data = {
            "unit_mix": [
                {"section": "NON-CLIMATE", "unit_type": "10 x 15", "size": "10 x 15", "num_units": 20}
            ]
        }

        discrepancies = detect_discrepancies(om_data, rent_roll_data, {})

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "unit_mix"
        assert "OM-only buckets" in discrepancies[0]["note"]

    def test_unit_mix_matching_rows_no_warning(self):
        om_data = {
            "unit_mix": [
                {"section": "NON-CLIMATE", "unit_type": "10 x 10", "size": "10 x 10", "num_units": 64}
            ]
        }
        rent_roll_data = {
            "unit_mix": [
                {"section": "NON-CLIMATE", "unit_type": "10 x 10", "size": "10 x 10", "num_units": 64}
            ]
        }

        discrepancies = detect_discrepancies(om_data, rent_roll_data, {})

        assert discrepancies == []

    def test_sqft_delta_1pct_boundary_triggers_warning(self):
        """Delta exactly 1% → info level (threshold is >= 1%)."""
        om_data = {"rentable_sqft": 75_000}
        rent_roll_data = {"summary": {"total_sqft": 74_250}}  # 1% lower
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert len(discrepancies) == 1
        assert discrepancies[0]["field"] == "rentable_sqft"
        assert discrepancies[0]["severity"] == "info"


class TestDiscrepancyMissingDocs:
    """Edge case: missing document data (empty dicts)."""

    def test_all_dicts_empty_no_crash(self):
        """All three dicts empty → no crash, empty list."""
        om_data = {}
        rent_roll_data = {}
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        assert discrepancies == []

    def test_om_missing_entire_rule_skipped(self):
        """OM missing all fields → rules involving OM skipped."""
        om_data = {}
        rent_roll_data = {
            "summary": {
                "total_units": 150,
                "occupancy_pct": 0.92,
            }
        }
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        # No unit count comparison (OM missing)
        assert discrepancies == []

    def test_rent_roll_summary_missing(self):
        """Rent roll lacks 'summary' key → no comparison made, no discrepancy."""
        om_data = {"num_units": 150}
        rent_roll_data = {}  # No summary
        t12_data = {}

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        # No comparison possible without rent_roll summary
        assert len(discrepancies) == 0


class TestDiscrepancyMultiple:
    """Multiple rules triggering in same run."""

    def test_multiple_discrepancies(self):
        """Multiple mismatches → all reported."""
        om_data = {
            "num_units": 150,
            "occupancy_pct": 0.93,
            "gross_potential_rent_annual": 600_000,
            "opex_pct": 0.40,
        }
        rent_roll_data = {
            "summary": {
                "total_units": 140,  # Mismatch
                "occupancy_pct": 0.88,  # Mismatch
                "annual_gross_potential_rent": 500_000,  # Mismatch
            }
        }
        t12_data = {
            "summary": {
                "opex_ratio": 0.37,  # Mismatch
            }
        }

        discrepancies = detect_discrepancies(om_data, rent_roll_data, t12_data)

        # Should have 4 discrepancies
        assert len(discrepancies) == 4
        fields = {d["field"] for d in discrepancies}
        assert fields == {"num_units", "occupancy_pct", "gross_potential_rent_annual", "opex_ratio"}
