"""Unit tests for the memo data assembler."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.verticals.real_estate.underwriting.memo.data_assembler import build_memo_context


def _run(inputs_overrides=None, artifact_overrides=None, document_ids=None, citation_context=None, field_citations=None):
    """Build a minimal Run-like object with sensible defaults."""
    inputs = {
        "project": {
            "name": "Test Storage",
            "asset_type": "self_storage",
            "address": "123 Test Ave",
            "num_units": 400,
            "rentable_sqft": 50_000,
            "year_built": 2010,
            "population_3mi": 60_000,
            "avg_household_income_3mi": 75_000.0,
            "storage_sqft_per_capita_3mi": 7.5,
            "nearby_storage_count_1mi": 2,
            "nearby_storage_count_3mi": 6,
            "nearby_storage_count_5mi": 11,
        },
        "acquisition": {
            "purchase_price": 5_000_000.0,
            "closing_cost_pct": 0.02,
            "capex_reserve_per_unit": 100.0,
            "market_cap_rate_purchase": 0.07,
        },
        "operational": {
            "gross_potential_rent_annual": 800_000.0,
            "vacancy_credit_loss_pct": 0.10,
            "other_income_annual": 0.0,
            "mgmt_fee_pct": 0.06,
            "rent_growth_pct": 0.03,
            "opex_growth_pct": 0.02,
            "insurance_annual": 0.0,
        },
        "financing": {
            "ltv_pct": 0.65,
            "interest_rate_pct": 0.065,
            "amortization_years": 25,
            "loan_term_years": 10,
        },
        "exit": {"hold_period_years": 10, "exit_cap_rate": 0.065, "selling_cost_pct": 0.03},
        "criteria": {
            "target_irr": 0.15,
            "target_cash_on_cash": 0.08,
            "max_ltv": 0.65,
            "dscr_year_one_floor": 1.25,
        },
        "unit_mix": [
            {"size": "10x10", "num_units": 100, "climate_type": "CC", "current_rent": 120.0},
            {"size": "10x10", "num_units": 200, "climate_type": "NC", "current_rent": 90.0},
            {"size": "10x20", "num_units": 100, "climate_type": "NC", "current_rent": 150.0},
        ],
        "rent_comps": [],
    }
    if inputs_overrides:
        for k, v in inputs_overrides.items():
            if isinstance(v, dict) and k in inputs and isinstance(inputs[k], dict):
                inputs[k].update(v)
            else:
                inputs[k] = v

    # Real SelfStorageResult shape — top-level metrics + projections list.
    artifact = {
        "irr": 0.18,
        "cash_on_cash": 0.09,
        "equity_multiple": 2.1,
        "dscr_year_one": 1.45,
        "debt_yield": 0.092,
        "break_even_occupancy_pct": 0.78,
        "noi_year_one": 400_000.0,
        "cap_rate_year_one": 0.08,
        "projections": [
            {
                "year": 1,
                "gpr": 800_000.0,
                "vacancy_loss": 80_000.0,
                "other_income": 0.0,
                "egi": 720_000.0,
                "opex": 320_000.0,
                "noi": 400_000.0,
                "debt_service": 250_000.0,
                "cash_flow": 150_000.0,
            }
        ],
        "noi_bridge": {"om_stated": 410_000.0, "modeled": 400_000.0, "delta": -10_000.0},
        "rent_position_analysis": [
            {
                "size": "10 x 10", "climate_type": "NC", "subject_current_rent": 110.0,
                "subject_market_rent": 115.0, "comp_average_rent": 120.0,
                "current_vs_comp_ratio": 0.917, "market_vs_comp_ratio": 0.958, "comp_count": 4,
            },
            {
                "size": "10 x 20", "climate_type": "NC", "subject_current_rent": 135.0,
                "subject_market_rent": 140.0, "comp_average_rent": 138.0,
                "current_vs_comp_ratio": 0.978, "market_vs_comp_ratio": 1.014, "comp_count": 3,
            },
        ],
        "stress_tests": [
            {"label": "Vacancy +500bps", "scenario_key": "vacancy_plus_500bps",
             "irr": 0.155, "cash_on_cash": 0.059, "dscr_year_one": 1.33, "equity_multiple": 2.41},
            {"label": "Rent Growth → 0%", "scenario_key": "rent_growth_zero",
             "irr": 0.038, "cash_on_cash": 0.076, "dscr_year_one": 1.43, "equity_multiple": 1.32},
        ],
        "rollover_risk": {"max_window_pct": 0.18},
        "projections": [
            {"year": 1, "gpr": 800_000.0, "vacancy_loss": 80_000.0, "other_income": 0.0,
             "egi": 720_000.0, "opex": 320_000.0, "noi": 400_000.0,
             "debt_service": 250_000.0, "cash_flow": 150_000.0},
            {"year": 2, "gpr": 824_000.0, "vacancy_loss": 82_400.0, "other_income": 0.0,
             "egi": 741_600.0, "opex": 326_400.0, "noi": 415_200.0,
             "debt_service": 250_000.0, "cash_flow": 165_200.0},
        ],
        "capital_structure": {
            "purchase_price": 5_000_000.0,
            "down_payment": 1_750_000.0,
            "loan_amount": 3_250_000.0,
            "closing_cost": 100_000.0,
            "capex_reserve_initial": 40_000.0,
            "total_equity_invested": 1_890_000.0,
        },
        "verdict": {"rationale": "All return metrics exceed criteria."},
    }
    if artifact_overrides:
        artifact.update(artifact_overrides)

    return SimpleNamespace(
        id="run-1",
        user_id="user-1",
        name="Test Storage",
        address="123 Test Ave",
        inputs=inputs,
        result_artifact=artifact,
        document_ids=document_ids or ["doc-om-1"],
        citation_context=citation_context,
        field_citations=field_citations or {},
        # Run-level columns populated by the calculator
        irr=0.18,
        cash_on_cash=0.09,
        equity_multiple=2.1,
        dscr_year_one=1.45,
        cap_rate_year_one=0.08,
        noi_year_one=400_000.0,
        verdict_status="worth_pursuing",
        verdict_failures=[
            {"metric": "DSCR stress", "actual": "1.15", "target": "1.25"},
        ],
    )


def _memo(cover=None, sponsor=None, notes=None, thesis=None):
    return SimpleNamespace(
        id="memo-1",
        cover_data=cover or {"deal_name": "Test Storage", "prepared_by": "Alice", "firm": "Acme", "date": "2026-05-20", "address": "123 Test Ave"},
        sponsor_data=sponsor or {},
        market_notes=notes,
        thesis_data=thesis or {},
    )


class TestBuildMemoContext:
    def test_pulls_identity_and_physical_from_inputs_project(self):
        ctx = build_memo_context(_run(), _memo())
        assert ctx.deal_name == "Test Storage"
        assert ctx.address == "123 Test Ave"
        assert ctx.asset_type == "self_storage"
        assert ctx.year_built == 2010
        assert ctx.num_units == 400
        assert ctx.rentable_sqft == 50_000

    def test_derives_climate_control_breakdown(self):
        ctx = build_memo_context(_run(), _memo())
        # CC = 100 units, NC = 200 + 100 = 300 units, total = 400
        assert ctx.cc_unit_count == 100
        assert ctx.nc_unit_count == 300
        assert ctx.climate_control_pct == pytest.approx(0.25)

    def test_computes_price_per_unit_and_sqft(self):
        ctx = build_memo_context(_run(), _memo())
        assert ctx.price_per_unit == pytest.approx(12_500.0)
        assert ctx.price_per_sqft == pytest.approx(100.0)

    def test_passes_through_demographics(self):
        ctx = build_memo_context(_run(), _memo())
        assert ctx.population_3mi == 60_000
        assert ctx.avg_household_income_3mi == 75_000.0
        assert ctx.storage_sqft_per_capita_3mi == 7.5
        assert ctx.nearby_storage_3mi == 6

    def test_pulls_verdict_and_artifact_blocks(self):
        ctx = build_memo_context(_run(), _memo())
        # verdict_status "worth_pursuing" maps to "Pursue"
        assert ctx.classification == "Pursue"
        # warnings synthesized from verdict_failures rows
        assert any("DSCR" in w for w in ctx.warnings)
        # Return metrics carry the calculator's real key names (single vocabulary).
        assert ctx.return_metrics["dscr_year_one"] == 1.45
        assert ctx.return_metrics["cash_on_cash"] == 0.09
        assert ctx.return_metrics["equity_multiple"] == 2.1
        # NOI buildup is a pass-through of projections[0]'s AnnualProjection shape.
        assert ctx.noi_buildup["noi"] == 400_000.0
        assert ctx.noi_buildup["gpr"] == 800_000.0
        assert ctx.noi_buildup["vacancy_loss"] == 80_000.0

    def test_max_loan_computed_inline_when_inputs_present(self):
        """The renderer's loan-sizing table reads max_loan_by_dscr/ltv/debt_yield
        plus binding_constraint. These are computed by calculate_max_loan at
        memo-build time (not persisted on the run)."""
        ctx = build_memo_context(_run(), _memo())
        # Inputs in the fixture support computing all three constraints.
        assert ctx.max_loan["max_loan"] is not None
        assert ctx.max_loan["binding_constraint"] in {"dscr", "ltv", "debt_yield"}
        assert ctx.max_loan["current_loan"] == 5_000_000.0 * 0.65
        assert ctx.max_loan["delta_vs_current"] is not None

    def test_verdict_status_maps_to_classification(self):
        for status, expected in [
            ("worth_pursuing", "Pursue"),
            ("needs_review", "Needs Review"),
            ("below_standards", "Below Screen"),
        ]:
            run = _run()
            run.verdict_status = status
            ctx = build_memo_context(run, _memo())
            assert ctx.classification == expected

    def test_thesis_data_plumbed_through(self):
        memo = _memo()
        memo.thesis_data = {
            "thesis_text": "Acquire at attractive basis; convert parking to NC storage for +$120K NOI.",
            "strategy_type": "Conversion",
            "hold_period_years": 7,
            "verdict_override": "Pursue",
            "verdict_override_reason": "Conversion thesis dominates the verdict's static read.",
            "custom_conditions": ["Phase I ordered", "PCA scheduled", "  ", ""],  # blanks filtered
            "sourcing_type": "Off-market",
            "sourcing_detail": "Repeat seller (Anderson Storage)",
        }
        ctx = build_memo_context(_run(), memo)
        assert ctx.thesis_text.startswith("Acquire")
        assert ctx.strategy_type == "Conversion"
        assert ctx.hold_period_years_override == 7
        assert ctx.verdict_override == "Pursue"
        assert ctx.verdict_override_reason.startswith("Conversion thesis")
        assert ctx.custom_conditions == ["Phase I ordered", "PCA scheduled"]
        assert ctx.sourcing_type == "Off-market"
        assert ctx.sourcing_detail.startswith("Repeat seller")

    def test_verdict_override_wins_over_calculator(self):
        """Analyst override of 'Below Screen' → 'Pursue' must change effective
        classification while preserving calculator's verdict for audit trail."""
        run = _run()
        run.verdict_status = "below_standards"  # calculator says Below Screen
        memo = _memo()
        memo.thesis_data = {
            "verdict_override": "Pursue",
            "verdict_override_reason": "Off-screen rationale.",
        }
        ctx = build_memo_context(run, memo)
        assert ctx.classification == "Pursue"
        assert ctx.classification_calculator == "Below Screen"
        assert ctx.verdict_override == "Pursue"

    def test_invalid_verdict_override_is_ignored(self):
        run = _run()
        run.verdict_status = "below_standards"
        memo = _memo()
        memo.thesis_data = {"verdict_override": "Maybe"}  # not a valid value
        ctx = build_memo_context(run, memo)
        # Falls back to calculator's verdict
        assert ctx.classification == "Below Screen"
        assert ctx.verdict_override is None

    def test_empty_thesis_data_yields_none_fields(self):
        memo = _memo()
        memo.thesis_data = {}
        ctx = build_memo_context(_run(), memo)
        assert ctx.thesis_text is None
        assert ctx.strategy_type is None
        assert ctx.verdict_override is None
        assert ctx.custom_conditions == []

    def test_optional_fields_fall_through_as_none(self):
        run = _run(inputs_overrides={"project": {"year_built": None, "rentable_sqft": None}})
        ctx = build_memo_context(run, _memo())
        assert ctx.year_built is None
        assert ctx.rentable_sqft is None
        # price_per_sqft should be None because rentable_sqft is None
        assert ctx.price_per_sqft is None

    def test_unit_mix_truncated_above_20_rows(self):
        big_mix = [
            {"size": f"unit-{i}", "num_units": 1, "climate_type": "NC", "current_rent": 100.0}
            for i in range(25)
        ]
        run = _run(inputs_overrides={"unit_mix": big_mix})
        ctx = build_memo_context(run, _memo())
        assert len(ctx.unit_mix) == 20

    def test_rent_comps_truncated_above_20_rows(self):
        big_comps = [
            {"facility": f"F{i}", "size": "10x10", "asking_rent": 100.0, "rent_per_sqft": 1.0}
            for i in range(25)
        ]
        run = _run(inputs_overrides={"rent_comps": big_comps})
        ctx = build_memo_context(run, _memo())
        assert len(ctx.rent_comps) == 20

    def test_passes_through_form_data(self):
        memo = _memo(
            cover={"deal_name": "X", "prepared_by": "Y", "firm": "Z", "date": "2026-05-20", "address": "A"},
            sponsor={"sponsor_name": "Acme Sponsor", "experience": "10 deals"},
            notes="Submarket is heating up.",
        )
        ctx = build_memo_context(_run(), memo)
        assert ctx.cover_data["firm"] == "Z"
        assert ctx.sponsor_data["sponsor_name"] == "Acme Sponsor"
        assert ctx.market_notes == "Submarket is heating up."

    def test_extracts_om_document_ids_from_dict_shape(self):
        """Production schema stores document_ids as [{document_id, doc_type}, ...]."""
        run = _run(document_ids=[
            {"document_id": "doc-om-1", "doc_type": "om"},
            {"document_id": "doc-t12-1", "doc_type": "t12"},
            {"document_id": "doc-om-2", "doc_type": "om"},
        ])
        ctx = build_memo_context(run, _memo())
        assert ctx.document_ids == ["doc-om-1", "doc-om-2"]

    def test_document_ids_accepts_bare_strings_for_back_compat(self):
        run = _run(document_ids=["doc-a", "doc-b"])
        ctx = build_memo_context(run, _memo())
        assert ctx.document_ids == ["doc-a", "doc-b"]

    def test_source_labels_prefer_citation_context_filename(self):
        run = _run(
            document_ids=[{"document_id": "doc-om-1", "doc_type": "om"}],
            citation_context={
                "S1:p10": {
                    "document_id": "doc-om-1",
                    "filename": "Tulsa Storage OM.pdf",
                    "page": 10,
                }
            },
        )
        ctx = build_memo_context(run, _memo())
        assert ctx.citation_doc_labels["doc-om-1"] == "Tulsa Storage OM.pdf"

    def test_source_labels_fallback_to_doc_type_not_uuid(self):
        run = _run(document_ids=[{"document_id": "doc-om-1", "doc_type": "om"}])
        ctx = build_memo_context(run, _memo())
        assert ctx.citation_doc_labels["doc-om-1"] == "Offering Memorandum"

    def test_builds_key_input_source_support_from_field_citations(self):
        run = _run(
            document_ids=[{"document_id": "doc-om-1", "doc_type": "om"}],
            citation_context={
                "S1:p6": {
                    "document_id": "doc-om-1",
                    "filename": "Tulsa Storage OM.pdf",
                    "page": 6,
                }
            },
            field_citations={
                "purchase_price": {
                    "doc_type": "om",
                    "confidence": 0.95,
                    "citations": ["S1:p6"],
                    "source_text": "Purchase Price: $5,000,000",
                },
                "num_units": {
                    "doc_type": "manual",
                    "is_manual": True,
                    "manual_override": True,
                    "original_value": 205,
                    "original_citation": {
                        "doc_type": "om",
                        "confidence": 0.95,
                        "citations": ["S1:p6"],
                        "source_text": "Total Units: 205",
                    },
                },
                "max_ltv": {
                    "doc_type": "om",
                    "is_default": True,
                    "confidence": 0,
                    "selection_note": "Used default max LTV assumption because OM max LTV was unavailable.",
                    "preferred_sources_missing": ["OM max LTV"],
                },
            },
        )

        ctx = build_memo_context(run, _memo())
        rows = {row["field_key"]: row for row in ctx.source_support}

        assert rows["purchase_price"]["source_basis"] == "OM stated"
        assert rows["purchase_price"]["citations"] == "Tulsa Storage OM.pdf: p6"
        assert rows["purchase_price"]["confidence"] == "95%"
        assert rows["num_units"]["source_basis"] == "Manual override"
        assert rows["num_units"]["citations"] == "Tulsa Storage OM.pdf: p6"
        assert rows["num_units"]["label"] == "Underwriting Unit Count"
        assert "original value 205" in rows["num_units"]["notes"]
        assert rows["max_ltv"]["source_basis"] == "Model default"
        assert "Missing preferred source" in rows["max_ltv"]["notes"]

    def test_source_support_clarifies_underwriting_unit_count_when_unit_mix_differs(self):
        run = _run(
            inputs_overrides={
                "project": {"num_units": 133},
                "unit_mix": [
                    {"size": "10 x 10", "num_units": 133, "unit_category": "storage"},
                    {"size": "parking", "num_units": 72, "unit_category": "parking"},
                ],
            },
            field_citations={
                "num_units": {
                    "doc_type": "manual",
                    "is_manual": True,
                    "manual_override": True,
                    "original_value": 205,
                },
            },
        )

        ctx = build_memo_context(run, _memo())
        row = next(row for row in ctx.source_support if row["field_key"] == "num_units")

        assert row["label"] == "Underwriting Unit Count"
        assert row["value"] == "133"
        assert "205 total units/spaces" in row["notes"]
        assert "133 storage" in row["notes"]
        assert "72 non-storage" in row["notes"]

    def test_carries_full_projections_list(self):
        ctx = build_memo_context(_run(), _memo())
        assert len(ctx.projections) == 2
        assert ctx.projections[0]["year"] == 1
        assert ctx.projections[1]["noi"] == 415_200.0

    def test_carries_capital_structure(self):
        ctx = build_memo_context(_run(), _memo())
        assert ctx.capital_structure["loan_amount"] == 3_250_000.0
        assert ctx.capital_structure["total_equity_invested"] == 1_890_000.0

    def test_carries_rent_position_analysis(self):
        ctx = build_memo_context(_run(), _memo())
        assert len(ctx.rent_position_analysis) == 2
        assert ctx.rent_position_analysis[0]["size"] == "10 x 10"

    def test_rent_position_summary_aggregated_from_buckets(self):
        """When artifact has no top-level rent_position, summarize per-bucket data."""
        ctx = build_memo_context(_run(), _memo())
        # Averages computed from the two bucket rows in the fixture.
        assert ctx.rent_position["matched_bucket_count"] == 2
        assert ctx.rent_position["total_bucket_count"] == 2
        assert ctx.rent_position["current_ratio_bucket_count"] == 2
        # (0.917 + 0.978) / 2 = 0.9475
        assert ctx.rent_position["current_vs_comp_avg"] == pytest.approx(0.9475)

    def test_rent_position_summary_distinguishes_comp_coverage_from_ratio_coverage(self):
        """Comp coverage should not be collapsed into "no matched buckets" just
        because the subject rent ratio could not be computed."""
        run = _run(artifact_overrides={
            "rent_position_analysis": [
                {
                    "size": "5 x 10",
                    "climate_type": "NC",
                    "subject_current_rent": None,
                    "comp_average_rent": 75.0,
                    "current_vs_comp_ratio": None,
                    "market_vs_comp_ratio": None,
                    "comp_count": 4,
                },
                {
                    "size": "8 x 15",
                    "climate_type": "NC",
                    "subject_current_rent": 105.0,
                    "comp_average_rent": None,
                    "current_vs_comp_ratio": None,
                    "market_vs_comp_ratio": None,
                    "comp_count": 0,
                },
            ],
        })

        ctx = build_memo_context(run, _memo())

        assert ctx.rent_position["matched_bucket_count"] == 1
        assert ctx.rent_position["current_ratio_bucket_count"] == 0
        assert ctx.rent_position["total_bucket_count"] == 2
        assert ctx.rent_position["unmatched_bucket_count"] == 1
        assert ctx.rent_position["unmatched_sizes"] == ["8 x 15"]

    def test_rent_position_falls_back_to_saved_unit_mix_and_rent_comps(self):
        """Existing runs may have rent comps and unit mix but no persisted
        rent_position_analysis. Memo context should recompute the same derived
        rows the result UI can show."""
        run = _run(
            inputs_overrides={
                "unit_mix": [],
                "rent_comps": [
                    {
                        "facility": "Comp A",
                        "size": "10 x 10",
                        "standard_sqft": 100,
                        "asking_rent": 100.0,
                        "climate_type": "NC",
                    }
                ],
            },
            artifact_overrides={
                "unit_mix": [
                    {
                        "size": "10 x 10",
                        "standard_sqft": 100,
                        "num_units": 10,
                        "current_rent": 90.0,
                        "climate_type": "NC",
                        "unit_category": "storage",
                    }
                ],
                "rent_position_analysis": [],
            },
        )

        ctx = build_memo_context(run, _memo())

        assert len(ctx.rent_position_analysis) == 1
        assert ctx.rent_position["matched_bucket_count"] == 1
        assert ctx.rent_position["current_vs_comp_avg"] == pytest.approx(0.9)
        assert ctx.rent_position["exact_size_matched_count"] == 1
        assert ctx.rent_position["exact_size_total_count"] == 1

    def test_rent_position_exact_size_coverage_matches_result_ui_read(self):
        run = _run(
            inputs_overrides={
                "unit_mix": [
                    {"size": "5 x 10", "num_units": 1, "unit_category": "storage"},
                    {"size": "10 x 10", "num_units": 1, "unit_category": "storage"},
                    {"size": "12 x 40", "num_units": 1, "unit_category": "storage"},
                    {"size": "10 x 20", "num_units": 1, "unit_category": "parking"},
                ],
                "rent_comps": [
                    {"facility": "A", "size": "5 x 10", "asking_rent": 75},
                    {"facility": "B", "size": "10x10", "asking_rent": 110},
                    {"facility": "Market Average (Broker)", "size": "10 x 10", "asking_rent": 100, "is_broker_market_average": True},
                ],
            },
            artifact_overrides={"rent_position_analysis": []},
        )

        ctx = build_memo_context(run, _memo())

        assert ctx.rent_position["exact_size_matched_count"] == 2
        assert ctx.rent_position["exact_size_total_count"] == 3
        assert ctx.rent_position["exact_size_unmatched_sizes"] == ["12 x 40"]
        assert ctx.rent_position["facility_comp_row_count"] == 2
        assert ctx.rent_position["broker_benchmark_row_count"] == 1
