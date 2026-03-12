"""Verification pass for diligence findings."""
from __future__ import annotations

from typing import Dict, List, Tuple


def verify_findings(findings: List[dict]) -> Tuple[List[dict], Dict[str, int]]:
    """Attach deterministic verification status for trust/audit workflows."""
    verified = 0
    needs_review = 0

    verified_findings: List[dict] = []
    for finding in findings:
        cloned = {**finding}
        evidence_list = cloned.get("evidence_list") or []
        metadata_json = dict(cloned.get("metadata_json") or {})

        confidence = cloned.get("confidence")
        has_evidence = len(evidence_list) > 0

        status = "verified"
        reasons = []

        if not has_evidence:
            status = "needs_review"
            reasons.append("missing_evidence")
        if confidence is None or confidence < 0.7:
            status = "needs_review"
            reasons.append("low_confidence")

        if cloned.get("category") == "numeric_reconciliation":
            spread_ratio = (metadata_json or {}).get("spread_ratio")
            if spread_ratio is not None and spread_ratio < 1.35:
                status = "needs_review"
                reasons.append("weak_numeric_spread")

        metadata_json["verification"] = {
            "status": status,
            "reasons": reasons,
            "version": "v1",
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
        "total": len(verified_findings),
    }
