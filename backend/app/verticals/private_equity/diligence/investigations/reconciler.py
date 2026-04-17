"""Amendment claim reconciliation — pure function, zero side effects.

Given a set of claims and a contract-family map (base_doc_id → [amendment_docs]),
flags any claim whose source document participates in an amendment relationship.

Design invariants:
  - NO LLM calls, NO DB access, NO I/O of any kind.
  - Given the same inputs, always produces the same outputs (deterministic).
  - Never auto-flips a claim's stance — only adds reason codes + needs_review.
  - Safe to call with empty contract_families (no-op, zero overhead).

Reason codes added to claim metadata_json.decision_reason_codes:
  - "amendment_exists"       source doc has amendments; clause may be modified
  - "amendment_overlap"      both base and amendment doc have claims for the same signal
  - "potentially_superseded" base doc has an 'amended and restated' (supersedes) amendment
"""
from __future__ import annotations

from typing import Dict, List


def reconcile_amendment_claims(
    claims: List[dict],
    claim_evidence_map: Dict[str, List[dict]],
    contract_families: Dict[str, List[dict]],
) -> List[dict]:
    """Flag claims whose source documents have amendment relationships.

    Args:
        claims: Claim dicts (modified in place — reason codes appended).
        claim_evidence_map: {claim_key: [evidence_span_dicts]}.
            Evidence spans must contain "source_document_id".
        contract_families: {base_doc_id: [{amendment_doc_id, amendment_type, confidence}]}.
            Built from PEDiligenceRoomDocument.metadata_json["amendment_link"].

    Returns:
        The same claims list with reason codes appended where applicable.
    """
    if not contract_families or not claims:
        return claims

    # Build reverse lookups in O(total amendments) time.
    # amendment_to_base: {amendment_doc_id: base_doc_id}
    # superseded_bases: set of base_doc_ids that have a "supersedes" amendment
    amendment_to_base: Dict[str, str] = {}
    superseded_bases: set[str] = set()

    for base_doc_id, amendments in contract_families.items():
        for amend in amendments:
            amend_doc_id = amend.get("amendment_doc_id")
            if not amend_doc_id:
                continue
            amendment_to_base[amend_doc_id] = base_doc_id
            if amend.get("amendment_type") == "supersedes":
                superseded_bases.add(base_doc_id)

    # Set of base_doc_ids that have at least one amendment.
    bases_with_amendments: set[str] = set(contract_families.keys())

    # Index claims by their source document for the overlap check.
    # docs_with_claims: {doc_id: [claim_key]}
    docs_with_claims: Dict[str, List[str]] = {}
    for claim in claims:
        claim_key = claim.get("claim_key") or str(id(claim))
        for ev in claim_evidence_map.get(claim_key, []):
            src = ev.get("source_document_id")
            if src:
                docs_with_claims.setdefault(src, []).append(claim_key)
                break  # one source per claim is enough for index

    # Collect claim_keys that need overlap flagging (both base and amendment
    # in the same family each have at least one claim).
    overlap_claim_keys: set[str] = set()
    for base_doc_id in bases_with_amendments:
        base_claim_keys = docs_with_claims.get(base_doc_id, [])
        if not base_claim_keys:
            continue
        amend_ids_with_claims = [
            amend["amendment_doc_id"]
            for amend in contract_families[base_doc_id]
            if amend.get("amendment_doc_id") in docs_with_claims
        ]
        if amend_ids_with_claims:
            overlap_claim_keys.update(base_claim_keys)
            for amend_id in amend_ids_with_claims:
                overlap_claim_keys.update(docs_with_claims[amend_id])

    # Apply reason codes.
    for claim in claims:
        claim_key = claim.get("claim_key") or str(id(claim))
        evidence_spans = claim_evidence_map.get(claim_key, [])

        # Determine the source document for this claim.
        source_doc_id: str | None = None
        for ev in evidence_spans:
            source_doc_id = ev.get("source_document_id")
            if source_doc_id:
                break

        if not source_doc_id:
            continue

        reason_codes: list = list(
            claim.setdefault("metadata_json", {}).setdefault("decision_reason_codes", [])
        )

        # Rule 1: Claim from base doc that has amendments.
        if source_doc_id in bases_with_amendments:
            if "amendment_exists" not in reason_codes:
                reason_codes.append("amendment_exists")
            claim["verification_status"] = "needs_review"

        # Rule 2: Overlap — both base and amendment have claims.
        if claim_key in overlap_claim_keys:
            if "amendment_overlap" not in reason_codes:
                reason_codes.append("amendment_overlap")
            claim["verification_status"] = "needs_review"

        # Rule 3: Base doc has a superseding ("amended & restated") amendment.
        if source_doc_id in superseded_bases:
            if "potentially_superseded" not in reason_codes:
                reason_codes.append("potentially_superseded")
            claim["verification_status"] = "needs_review"

        # Write back (setdefault already wired to claim["metadata_json"]).
        claim["metadata_json"]["decision_reason_codes"] = reason_codes

    return claims
