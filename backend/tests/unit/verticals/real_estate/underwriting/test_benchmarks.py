"""Tests for self-storage underwriting benchmark constants."""
import pytest
from app.verticals.real_estate.underwriting.benchmarks import (
    BENCHMARKS,
    get_expense_floors,
)


def test_benchmarks_has_self_storage_key():
    assert "self_storage" in BENCHMARKS


def test_all_required_keys_present():
    ss = BENCHMARKS["self_storage"]
    required = {
        "repairs_per_sqft",
        "insurance_per_sqft",
        "utilities_per_sqft",
        "marketing_pct_egi",
        "mgmt_fee_pct_egi",
        "bank_fees_pct_egi",
    }
    assert required.issubset(ss.keys())


def test_each_benchmark_has_floor_and_typical():
    for key, val in BENCHMARKS["self_storage"].items():
        assert "floor" in val, f"{key} missing 'floor'"
        assert "typical" in val, f"{key} missing 'typical'"
        assert val["floor"] <= val["typical"], f"{key} floor exceeds typical"


def test_get_expense_floors_self_storage():
    floors = get_expense_floors("self_storage", rentable_sqft=21017.0, egi=283489.0)
    assert floors["repairs_maintenance_annual"] == pytest.approx(21017.0 * 0.10, rel=1e-6)
    assert floors["insurance_annual"] == pytest.approx(21017.0 * 0.35, rel=1e-6)
    assert floors["utilities_annual"] == pytest.approx(21017.0 * 0.25, rel=1e-6)
    assert floors["marketing_annual"] == pytest.approx(283489.0 * 0.03, rel=1e-6)


def test_get_expense_floors_unknown_asset_type_returns_empty():
    floors = get_expense_floors("multifamily", rentable_sqft=10000.0, egi=500000.0)
    assert floors == {}
