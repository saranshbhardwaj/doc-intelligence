from types import SimpleNamespace

from app.verticals.real_estate.underwriting.workflow.evaluator import evaluate_self_storage_workflow


def _run(**overrides):
    base = {
        "id": "run-1",
        "asset_type": "self_storage",
        "status": "completed",
        "document_ids": [{"document_id": "doc-1", "doc_type": "om"}],
        "inputs": {"criteria": {"target_irr": 0.15, "target_equity_multiple": 1.8, "max_ltv": 0.70, "dscr_year_one_floor": 1.25}},
        "field_citations": {"purchase_price": {"citations": ["S1:p1"]}},
        "citation_context": {},
        "discrepancies": [],
        "result_artifact": {
            "verdict": {"status": "worth_pursuing", "failures": [], "warnings": []},
            "plausibility_flags": [],
            "noi_bridge": {"delta_pct": -0.02},
            "rent_comps": [{"name": "Comp A"}],
        },
        "verdict_status": "worth_pursuing",
        "verdict_failures": [],
        "irr": 0.18,
        "equity_multiple": 2.1,
        "dscr_year_one": 1.45,
        "ltv": 0.65,
        "error_message": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def gate(state, gate_id):
    return next(item for item in state.gates if item.id == gate_id)


def phase(state, phase_id):
    return next(item for item in state.phases if item.id == phase_id)


def test_completed_passing_run_allows_memo_without_override():
    state = evaluate_self_storage_workflow(_run())

    assert state.workflow_key == "self_storage_acquisition_underwrite"
    assert state.memo_generation.allowed is True
    assert state.memo_generation.requires_override is False
    assert gate(state, "investment_screen").status == "passed"
    assert phase(state, "returns_debt").status == "passed"


def test_legacy_string_document_id_counts_as_om_like_source():
    state = evaluate_self_storage_workflow(_run(document_ids=["legacy-doc-id"]))

    data_quality_findings = gate(state, "data_quality").findings
    assert phase(state, "intake").status == "passed"
    assert "missing_om" not in {finding.id for finding in data_quality_findings}


def test_failed_extraction_blocks_data_quality():
    state = evaluate_self_storage_workflow(
        _run(status="failed", result_artifact=None, error_message="extraction failed")
    )

    assert phase(state, "extraction").status == "blocked"
    assert gate(state, "data_quality").status == "blocked"
    assert state.memo_generation.requires_override is True


def test_active_extraction_disables_memo_without_override():
    state = evaluate_self_storage_workflow(_run(status="extracting", result_artifact=None))

    assert phase(state, "extraction").status == "in_progress"
    assert state.memo_generation.allowed is False
    assert state.memo_generation.requires_override is False


def test_below_screen_verdict_blocks_investment_screen():
    state = evaluate_self_storage_workflow(
        _run(
            verdict_status="below_standards",
            verdict_failures=[{"metric": "IRR", "target": 0.15, "actual": 0.08}],
            result_artifact={"verdict": {"status": "below_standards", "failures": [{"metric": "IRR"}]}, "plausibility_flags": []},
            irr=0.08,
        )
    )

    assert gate(state, "investment_screen").status == "blocked"
    assert "investment_screen" in state.memo_generation.blocking_gate_ids
    assert state.memo_generation.requires_override is True


def test_unsupported_asset_type_returns_unsupported_state():
    state = evaluate_self_storage_workflow(_run(asset_type="multifamily"))

    assert state.workflow_key == "unsupported"
    assert state.memo_generation.allowed is False
    assert gate(state, "unsupported_asset_type").status == "blocked"