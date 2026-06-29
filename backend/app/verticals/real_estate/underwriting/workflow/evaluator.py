from __future__ import annotations

from typing import Any

from .schemas import (
    MemoGenerationState,
    UnderwritingWorkflowState,
    WorkflowFinding,
    WorkflowGate,
    WorkflowPhase,
)

WORKFLOW_NAME = "Self-Storage Acquisition Underwrite"
WORKFLOW_KEY = "self_storage_acquisition_underwrite"


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _has_om(run: Any) -> bool:
    docs = getattr(run, "document_ids", None) or []
    return any(
        (isinstance(doc, str) and bool(doc.strip()))
        or (isinstance(doc, dict) and (doc.get("doc_type") or "").lower() == "om")
        for doc in docs
    )


def _verdict_status(run: Any) -> str | None:
    if getattr(run, "verdict_status", None):
        return run.verdict_status
    verdict = _as_dict(_as_dict(getattr(run, "result_artifact", None)).get("verdict"))
    return verdict.get("status") or verdict.get("classification")


def _worst_status(findings: list[WorkflowFinding]) -> tuple[str, str]:
    if any(item.severity == "critical" for item in findings):
        return "blocked", "critical"
    if findings:
        return "needs_review", "warning"
    return "passed", "info"


def _unsupported(run: Any) -> UnderwritingWorkflowState:
    gate = WorkflowGate(
        id="unsupported_asset_type",
        label="Unsupported Asset Type",
        status="blocked",
        severity="critical",
        can_override=False,
        findings=[WorkflowFinding(
            id="unsupported_asset_type",
            severity="critical",
            message="Self-Storage Acquisition Underwrite is only available for self-storage runs.",
            source="run",
        )],
    )
    return UnderwritingWorkflowState(
        workflow_name="Unsupported Workflow",
        workflow_key="unsupported",
        asset_type=getattr(run, "asset_type", None),
        overall_status="blocked",
        memo_generation=MemoGenerationState(
            allowed=False,
            requires_override=False,
            blocking_gate_ids=[gate.id],
            disabled_reason="Unsupported asset type.",
        ),
        phases=[],
        gates=[gate],
    )


def evaluate_self_storage_workflow(run: Any, has_active_memo: bool = False, latest_memo: Any | None = None) -> UnderwritingWorkflowState:
    if getattr(run, "asset_type", None) != "self_storage":
        return _unsupported(run)

    artifact = _as_dict(getattr(run, "result_artifact", None))
    discrepancies = _as_list(getattr(run, "discrepancies", None))
    field_citations = _as_dict(getattr(run, "field_citations", None))
    inputs = _as_dict(getattr(run, "inputs", None))
    run_status = getattr(run, "status", None)

    data_findings: list[WorkflowFinding] = []
    if not _has_om(run):
        data_findings.append(WorkflowFinding(
            id="missing_om",
            severity="warning",
            message="No offering memorandum is attached to this run.",
            source="documents",
            related_section="source_documents",
        ))
    if run_status == "failed":
        data_findings.append(WorkflowFinding(
            id="extraction_failed",
            severity="critical",
            message=getattr(run, "error_message", None) or "Extraction failed for this run.",
            source="run.status",
            related_section="source_documents",
        ))
    if run_status not in {"extracting", "calculating"} and not artifact:
        data_findings.append(WorkflowFinding(
            id="missing_result_artifact",
            severity="critical",
            message="No calculated underwriting result is available.",
            source="result_artifact",
            related_section="returns",
        ))

    required_input_paths = [
        ("project", "num_units"),
        ("acquisition", "purchase_price"),
        ("operational", "gross_potential_rent_annual"),
        ("financing", "ltv_pct"),
        ("exit", "exit_cap_rate"),
    ]
    has_underwriting_sections = any(section in inputs for section, _field in required_input_paths)
    missing_paths = [
        f"{section}.{field}"
        for section, field in required_input_paths
        if has_underwriting_sections and _as_dict(inputs.get(section)).get(field) is None
    ]
    if missing_paths and artifact:
        data_findings.append(WorkflowFinding(
            id="missing_core_inputs",
            severity="critical",
            message="Critical assumptions are missing: " + ", ".join(missing_paths),
            source="inputs",
            related_section="operations",
        ))

    plausibility_flags = _as_list(artifact.get("plausibility_flags"))
    source_findings: list[WorkflowFinding] = []
    critical_discrepancies = [d for d in discrepancies if _as_dict(d).get("severity") in {"critical", "error"}]
    if critical_discrepancies:
        source_findings.append(WorkflowFinding(
            id="critical_discrepancies",
            severity="critical",
            message=f"{len(critical_discrepancies)} critical source discrepancy item(s) need review.",
            source="discrepancies",
            related_section="discrepancies",
        ))
    if plausibility_flags:
        source_findings.append(WorkflowFinding(
            id="plausibility_flags",
            severity="critical",
            message=f"{len(plausibility_flags)} implausible extracted value(s) were flagged.",
            source="result_artifact.plausibility_flags",
            related_section="evidence",
        ))
    for field in ("purchase_price", "gross_potential_rent_annual", "exit_cap_rate"):
        citation = _as_dict(field_citations.get(field))
        if artifact and citation.get("is_default"):
            source_findings.append(WorkflowFinding(
                id=f"default_assumption_{field}",
                severity="warning",
                message=f"Critical assumption `{field}` uses a default assumption: {citation.get('selection_note') or citation.get('formula') or 'No source value was available.'}",
                source="field_citations",
                related_section="evidence",
            ))
        elif artifact and not citation.get("citations"):
            source_findings.append(WorkflowFinding(
                id=f"missing_citation_{field}",
                severity="warning",
                message=f"Critical assumption `{field}` has no source citation.",
                source="field_citations",
                related_section="evidence",
            ))

    market_findings: list[WorkflowFinding] = []
    rent_comps = _as_list(inputs.get("rent_comps")) or _as_list(artifact.get("rent_comps"))
    rent_growth = _as_dict(inputs.get("operational")).get("rent_growth_pct")
    if artifact and not rent_comps:
        market_findings.append(WorkflowFinding(
            id="thin_rent_comp_support",
            severity="warning",
            message="No rent comps are available to support market/rent assumptions.",
            source="inputs.rent_comps",
            related_section="market",
        ))
    if rent_growth is not None and rent_growth > 0.04 and not rent_comps:
        market_findings.append(WorkflowFinding(
            id="unsupported_rent_growth",
            severity="warning",
            message="Rent growth exceeds 4.0% without rent comp support.",
            source="inputs.operational.rent_growth_pct",
            related_section="market",
        ))

    investment_findings: list[WorkflowFinding] = []
    verdict = _verdict_status(run)
    if verdict in {"below_standards", "below_screen", "Below Screen"}:
        investment_findings.append(WorkflowFinding(
            id="below_screen_verdict",
            severity="critical",
            message="The current underwriting verdict is Below Screen.",
            source="verdict",
            related_section="returns",
        ))
    criteria = _as_dict(inputs.get("criteria"))
    checks = [
        ("below_target_irr", "IRR", getattr(run, "irr", None), criteria.get("target_irr"), "<"),
        ("below_target_equity_multiple", "Equity multiple", getattr(run, "equity_multiple", None), criteria.get("target_equity_multiple"), "<"),
        ("below_dscr_floor", "Year-one DSCR", getattr(run, "dscr_year_one", None), criteria.get("dscr_year_one_floor"), "<"),
        ("above_max_ltv", "LTV", getattr(run, "ltv", None), criteria.get("max_ltv"), ">"),
    ]
    for finding_id, label, actual, threshold, op in checks:
        if actual is None or threshold is None:
            continue
        fails = actual < threshold if op == "<" else actual > threshold
        if fails:
            investment_findings.append(WorkflowFinding(
                id=finding_id,
                severity="critical",
                message=f"{label} does not clear threshold ({actual:.2f} vs {threshold:.2f}).",
                source="inputs.criteria",
                related_section="returns",
            ))

    memo_findings: list[WorkflowFinding] = []
    if has_active_memo:
        memo_findings.append(WorkflowFinding(
            id="active_memo_generation",
            severity="critical",
            message="A memo is already generating for this run.",
            source="underwriting_memos.status",
            related_section="memo_history",
        ))

    data_status, data_severity = _worst_status(data_findings)
    source_status, source_severity = _worst_status(source_findings)
    market_status, market_severity = _worst_status(market_findings)
    investment_status, investment_severity = _worst_status(investment_findings)
    memo_status, memo_severity = _worst_status(memo_findings)

    gates = [
        WorkflowGate(id="data_quality", label="Data Quality", status=data_status, severity=data_severity, findings=data_findings),
        WorkflowGate(id="source_reconciliation", label="Source Reconciliation", status=source_status, severity=source_severity, findings=source_findings),
        WorkflowGate(id="market_rent_support", label="Market/Rent Support", status=market_status, severity=market_severity, findings=market_findings),
        WorkflowGate(id="investment_screen", label="Investment Screen", status=investment_status, severity=investment_severity, findings=investment_findings),
        WorkflowGate(id="memo_readiness", label="Memo Readiness", status=memo_status, severity=memo_severity, can_override=not has_active_memo, findings=memo_findings),
    ]

    phases = [
        WorkflowPhase(id="intake", label="Intake", status="passed" if _has_om(run) else "needs_review", related_sections=["source_documents"]),
        WorkflowPhase(id="extraction", label="Extraction", status="in_progress" if run_status in {"extracting", "calculating"} else ("blocked" if run_status == "failed" else "passed"), related_sections=["source_documents"]),
        WorkflowPhase(id="source_reconciliation", label="Source Reconciliation", status=source_status, related_sections=["evidence", "discrepancies"]),
        WorkflowPhase(id="market_rent_support", label="Market/Rent Support", status=market_status, related_sections=["market"]),
        WorkflowPhase(id="returns_debt", label="Returns & Debt", status=investment_status, related_sections=["returns", "scenario", "max_loan"]),
        WorkflowPhase(id="risk_review", label="Risk Review", status="blocked" if investment_status == "blocked" else "needs_review" if any(g.status == "needs_review" for g in gates) else "passed", related_sections=["verdict", "evidence"]),
        WorkflowPhase(id="ic_memo", label="IC Memo", status="in_progress" if has_active_memo else ("needs_review" if getattr(latest_memo, "generated_with_override", False) else "not_started"), related_sections=["memo_history"]),
        WorkflowPhase(id="memo_audit", label="Memo Audit", status="not_started", related_sections=["memo_history"]),
    ]

    hard_disabled = run_status in {"extracting", "calculating"} or has_active_memo
    blocking_gate_ids = [gate.id for gate in gates if gate.status == "blocked" and gate.can_override]
    non_override_blockers = [gate.id for gate in gates if gate.status == "blocked" and not gate.can_override]
    requires_override = bool(blocking_gate_ids) and not hard_disabled
    allowed = bool(artifact) and not hard_disabled and not non_override_blockers and not (blocking_gate_ids and not requires_override)
    disabled_reason = None
    if run_status in {"extracting", "calculating"}:
        disabled_reason = "Extraction or calculation is still running."
    elif has_active_memo:
        disabled_reason = "A memo is already generating for this run."
    elif not artifact:
        disabled_reason = "No calculated underwriting result is available."

    overall_status = "blocked" if any(g.status == "blocked" for g in gates) else "needs_review" if any(g.status == "needs_review" for g in gates) else "passed"
    return UnderwritingWorkflowState(
        workflow_name=WORKFLOW_NAME,
        workflow_key=WORKFLOW_KEY,
        asset_type="self_storage",
        overall_status=overall_status,
        memo_generation=MemoGenerationState(
            allowed=allowed,
            requires_override=requires_override,
            blocking_gate_ids=blocking_gate_ids,
            disabled_reason=disabled_reason,
        ),
        phases=phases,
        gates=gates,
    )