"""Coverage scoring for investigations.

Coverage measures how thoroughly the investigation scanned the data room.
It weights document types: contracts and legal docs matter more than
marketing materials for a CoC investigation.

Scoring breakdown (weights sum to 1.0):
    0.35  contract coverage ratio  -- contracts with hits / total contracts
    0.25  overall doc spread       -- docs with hits / total docs
    0.15  targeted doc spread      -- docs with hits / targeted docs
    0.25  evidence density         -- evidence span count (capped at 10)
"""
from __future__ import annotations

from typing import Dict, Optional, Sequence


# Document types considered "high-value" for investigation coverage.
# These carry 3x weight in coverage scoring.
_CONTRACT_TYPES = frozenset({"purchase_agreement", "legal_contract"})
# Medium-value document types (1.5x weight).
_FINANCIAL_TYPES = frozenset({"financial_statement", "qoe_report"})


def compute_coverage_metrics(
    *,
    total_documents: int,
    targeted_documents: int,
    scanned_chunks: int,
    evidence_rows: Sequence[dict],
    retrieval_mode: str,
    document_classifications: Optional[Dict[str, dict]] = None,
) -> Dict[str, float]:
    """Compute coverage metrics for an investigation run.

    Args:
        document_classifications: Optional dict mapping document_id to
            classification info (``{"document_type": str, ...}``).
            When provided, enables document-type-weighted scoring.
    """
    evidence_doc_ids = {
        row.get("document_id")
        for row in evidence_rows
        if row.get("document_id")
    }
    evidence_span_count = len(evidence_rows)
    documents_with_hits = len(evidence_doc_ids)

    # ── Classify documents by importance ──────────────────────────
    classifications = document_classifications or {}
    contract_doc_ids: set = set()
    financial_doc_ids: set = set()
    other_doc_ids: set = set()

    if classifications:
        for doc_id, info in classifications.items():
            info = info if isinstance(info, dict) else {}
            doc_type = info.get("document_type") or "other"
            if doc_type in _CONTRACT_TYPES:
                contract_doc_ids.add(doc_id)
            elif doc_type in _FINANCIAL_TYPES:
                financial_doc_ids.add(doc_id)
            else:
                other_doc_ids.add(doc_id)

    contracts_with_hits = len(evidence_doc_ids & contract_doc_ids)
    total_contracts = len(contract_doc_ids)

    # ── Compute weighted coverage score ──────────────────────────
    has_classifications = bool(classifications)

    if has_classifications and total_contracts > 0:
        # Weighted scoring: contracts matter most.
        contract_coverage = contracts_with_hits / total_contracts
        doc_spread = (
            documents_with_hits / max(1, total_documents)
            if total_documents > 0 else 0.0
        )
        targeted_spread = (
            documents_with_hits / max(1, targeted_documents)
            if targeted_documents > 0 else 0.0
        )
        evidence_density = min(1.0, evidence_span_count / 10.0)

        coverage = (
            0.35 * min(1.0, contract_coverage)
            + 0.25 * min(1.0, doc_spread)
            + 0.15 * min(1.0, targeted_spread)
            + 0.25 * evidence_density
        )
    elif has_classifications and total_contracts == 0:
        # No contracts in VDR — force weak if no evidence at all,
        # otherwise use unweighted scoring.
        doc_spread = (
            documents_with_hits / max(1, total_documents)
            if total_documents > 0 else 0.0
        )
        targeted_spread = (
            documents_with_hits / max(1, targeted_documents)
            if targeted_documents > 0 else 0.0
        )
        evidence_density = min(1.0, evidence_span_count / 10.0)

        coverage = (
            0.40 * min(1.0, doc_spread)
            + 0.25 * min(1.0, targeted_spread)
            + 0.35 * evidence_density
        )
    else:
        # No classifications available — fall back to original unweighted.
        coverage = 0.0
        if total_documents > 0:
            coverage += min(0.4, (documents_with_hits / max(1, total_documents)) * 0.4)
        if targeted_documents > 0:
            coverage += min(0.25, (documents_with_hits / max(1, targeted_documents)) * 0.25)
        coverage += min(0.35, evidence_span_count / 10.0 * 0.35)

    # ── Force weak if contracts exist but none had hits ──────────
    if has_classifications and total_contracts > 0 and contracts_with_hits == 0:
        coverage = min(coverage, 0.39)  # Cap below "moderate" threshold

    # ── Determine status ─────────────────────────────────────────
    if coverage >= 0.7:
        coverage_status = "strong"
    elif coverage >= 0.4:
        coverage_status = "moderate"
    else:
        coverage_status = "weak"

    return {
        "documents_total": total_documents,
        "documents_targeted": targeted_documents,
        "documents_with_hits": documents_with_hits,
        "chunks_scanned": scanned_chunks,
        "chunks_with_hits": evidence_span_count,
        "distinct_docs_in_evidence": documents_with_hits,
        "evidence_span_count": evidence_span_count,
        "retrieval_mode": retrieval_mode,
        "coverage_score": round(coverage, 3),
        "coverage_status": coverage_status,
        # New: contract-specific metrics
        "contracts_total": total_contracts,
        "contracts_with_hits": contracts_with_hits,
        "contract_coverage_ratio": (
            round(contracts_with_hits / total_contracts, 3)
            if total_contracts > 0 else None
        ),
    }


def should_expand_search(metrics: Dict[str, float]) -> bool:
    """Decide whether to expand search from targeted to all documents."""
    return (
        int(metrics.get("distinct_docs_in_evidence", 0)) < 1
        or int(metrics.get("evidence_span_count", 0)) < 2
        or str(metrics.get("coverage_status")) == "weak"
    )
