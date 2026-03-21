"""Verification pass for diligence findings."""
from __future__ import annotations

from typing import Dict, List, Tuple


def verify_findings(findings: List[dict]) -> Tuple[List[dict], Dict[str, int]]:
    """Attach deterministic verification status for trust/audit workflows."""
    verified = 0
    needs_review = 0
    specialist_review = 0
    underwriting_only = 0
    evidence_gaps = 0
    high_priority_review = 0

    verified_findings: List[dict] = []
    for finding in findings:
        cloned = {**finding}
        evidence_list = cloned.get("evidence_list") or []
        metadata_json = dict(cloned.get("metadata_json") or {})
        workflow = dict(metadata_json.get("workflow") or {})

        confidence = cloned.get("confidence")
        has_evidence = len(evidence_list) > 0
        severity = cloned.get("severity") or "medium"
        source_kind = metadata_json.get("source_kind")
        workflow_bucket = workflow.get("bucket")
        owner_hint = workflow.get("owner_hint")

        status = "verified"
        reasons = []
        review_priority = "normal"
        analyst_action = workflow.get("next_step_hint")

        if not has_evidence:
            status = "needs_review"
            reasons.append("missing_evidence")
            evidence_gaps += 1
        if confidence is None or confidence < 0.7:
            status = "needs_review"
            reasons.append("low_confidence")

        if cloned.get("category") == "numeric_reconciliation":
            spread_ratio = (metadata_json or {}).get("spread_ratio")
            if spread_ratio is not None and spread_ratio < 1.35:
                status = "needs_review"
                reasons.append("weak_numeric_spread")

        if workflow_bucket == "specialist_review" or owner_hint == "specialist":
            status = "needs_review"
            reasons.append("specialist_review_required")
            specialist_review += 1

        if workflow_bucket == "underwriting_input":
            underwriting_only += 1
            if confidence is None or confidence < 0.85:
                status = "needs_review"
                reasons.append("underwriting_needs_confirmation")

        if source_kind == "cross_document_synthesis" and not cloned.get("source_document_id"):
            status = "needs_review"
            reasons.append("weak_cross_document_linkage")

        if severity == "high" and status == "needs_review":
            review_priority = "high"
            high_priority_review += 1
        elif workflow_bucket in {"specialist_review", "ic_blocker"}:
            review_priority = "high"
        elif reasons:
            review_priority = "medium"

        metadata_json["verification"] = {
            "status": status,
            "reasons": sorted(set(reasons)),
            "review_priority": review_priority,
            "analyst_action": analyst_action,
            "workflow_bucket": workflow_bucket,
            "owner_hint": owner_hint,
            "version": "v2",
        }
        cloned["metadata_json"] = metadata_json

        if status == "verified":
            verified += 1
        else:
            needs_review += 1

        verified_findings.append(cloned)

    return verified_findings, {
        "verified": verified,
        "needs_review": needs_review,
        "specialist_review": specialist_review,
        "underwriting_only": underwriting_only,
        "evidence_gaps": evidence_gaps,
        "high_priority_review": high_priority_review,
        "total": len(verified_findings),
    }
