"""Unit tests for underwriting result-artifact preservation helpers."""

from app.verticals.real_estate.underwriting.result_artifact import (
    get_preserved_unit_mix,
    merge_preserved_result_artifact,
)


def test_merge_preserved_result_artifact_keeps_existing_evidence_blocks():
    existing_artifact = {
        "om_data": {"num_units": 120},
        "rent_roll_data": {"summary": {"total_units": 118}},
        "t12_data": {"summary": {"opex_ratio": 0.41}},
        "demographics": {"population": 54000},
        "market_data": {"submarket_avg_cap_rate": 0.061},
        "rent_comps": [{"facility": "Comp A"}],
        "plausibility_flags": [{"field": "avg_market_rent_per_unit_monthly"}],
        "noi_bridge": {"rows": [{"label": "OM Year-1 NOI", "value": 100_000}]},
    }
    recalculated_artifact = {
        "irr": 0.18,
        "cash_on_cash": 0.09,
        "verdict": {"status": "worth_pursuing"},
    }

    merged_artifact = merge_preserved_result_artifact(existing_artifact, recalculated_artifact)

    assert merged_artifact["irr"] == 0.18
    assert merged_artifact["cash_on_cash"] == 0.09
    assert merged_artifact["verdict"] == {"status": "worth_pursuing"}
    assert merged_artifact["om_data"] == {"num_units": 120}
    assert merged_artifact["rent_roll_data"] == {"summary": {"total_units": 118}}
    assert merged_artifact["t12_data"] == {"summary": {"opex_ratio": 0.41}}
    assert merged_artifact["demographics"] == {"population": 54000}
    assert merged_artifact["market_data"] == {"submarket_avg_cap_rate": 0.061}
    assert merged_artifact["rent_comps"] == [{"facility": "Comp A"}]
    assert merged_artifact["plausibility_flags"] == [{"field": "avg_market_rent_per_unit_monthly"}]
    assert merged_artifact["noi_bridge"] == {"rows": [{"label": "OM Year-1 NOI", "value": 100_000}]}


def test_merge_preserved_result_artifact_does_not_override_new_values():
    existing_artifact = {
        "om_data": {"num_units": 120},
        "market_data": {"submarket_avg_cap_rate": 0.061},
    }
    recalculated_artifact = {
        "market_data": {"submarket_avg_cap_rate": 0.058},
        "verdict": {"status": "worth_pursuing"},
    }

    merged_artifact = merge_preserved_result_artifact(existing_artifact, recalculated_artifact)

    assert merged_artifact["market_data"] == {"submarket_avg_cap_rate": 0.058}
    assert merged_artifact["om_data"] == {"num_units": 120}


def test_get_preserved_unit_mix_prefers_rent_roll_then_top_level_then_om():
    existing_artifact = {
        "om_data": {"unit_mix": [{"section": "OM", "num_units": 10}]},
        "unit_mix": [{"section": "RESULT", "num_units": 20}],
        "rent_roll_data": {"unit_mix": [{"section": "RR", "num_units": 30}]},
    }

    preserved = get_preserved_unit_mix(existing_artifact)

    assert preserved == [{"section": "RR", "num_units": 30}]


def test_get_preserved_unit_mix_falls_back_to_om_unit_mix_when_needed():
    existing_artifact = {
        "om_data": {"unit_mix": [{"section": "UNCOVERED PARKING", "unit_type": "Parking", "num_units": 52}]},
        "unit_mix": [],
    }

    preserved = get_preserved_unit_mix(existing_artifact)

    assert preserved == [{"section": "UNCOVERED PARKING", "unit_type": "Parking", "num_units": 52}]
