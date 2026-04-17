"""Deterministic claim builder for change-of-control investigations.

Architecture
------------
PatternEntry     -- immutable description of a single regex signal
SIGNAL_REGISTRY  -- ordered list of patterns, grouped by signal category
_collect_hits    -- scans chunks against registry, deduplicates per (chunk, signal)
build_change_of_control_claims -- adjudicates claims from collected hits

Signal groups drive claim adjudication:
  change_of_control   -> positive evidence for Claim A (consent required)
  assignment_consent   -> positive evidence for Claim A (consent required)
  termination_on_coc   -> positive evidence for Claim B (termination exposure)
  consent_not_required -> negative evidence (contra Claim A)

Extension:
  Add new patterns to SIGNAL_REGISTRY to expand recall without modifying
  claim adjudication logic.  Add new investigation types by creating
  parallel registry + builder functions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Sequence, Tuple


# ---------------------------------------------------------------------------
# Negation detection
# ---------------------------------------------------------------------------
# Conservative approach: negation lowers confidence, never flips signal.
# Avoids masking real clauses when double-negation is present
# (e.g. "shall not assign without consent" is restrictive, not negated).

_NEGATION_WINDOW = 40  # chars before match start to scan
_NEGATION_RE = re.compile(
    r"\b(no|not|neither|nor|lacks?|absence\s+of|does\s+not|is\s+not|has\s+not)\b",
    re.IGNORECASE,
)
_NEGATION_CONFIDENCE_PENALTY = 0.12


# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PatternEntry:
    """Immutable regex pattern with signal metadata."""
    signal: str
    pattern: re.Pattern
    confidence: float
    label: str


SIGNAL_REGISTRY: List[PatternEntry] = [
    # ── change_of_control ──────────────────────────────────────────────
    PatternEntry(
        signal="change_of_control",
        pattern=re.compile(r"\bchange[\s-]*of[\s-]*control\b", re.IGNORECASE),
        confidence=0.90,
        label="Explicit change-of-control clause",
    ),
    PatternEntry(
        signal="change_of_control",
        pattern=re.compile(
            r"\btransfer\s+of\s+(?:a\s+)?controlling\s+interest\b", re.IGNORECASE
        ),
        confidence=0.86,
        label="Transfer of controlling interest",
    ),
    PatternEntry(
        signal="change_of_control",
        pattern=re.compile(
            r"\bacquisition\s+of\s+(?:a\s+)?majority\s+"
            r"(?:stake|interest|ownership|equity|shares?|stock)\b",
            re.IGNORECASE,
        ),
        confidence=0.82,
        label="Majority stake acquisition",
    ),
    PatternEntry(
        signal="change_of_control",
        pattern=re.compile(
            r"\bmerger\s+(?:or|and)\s+(?:consolidation|acquisition)\b", re.IGNORECASE
        ),
        confidence=0.84,
        label="Merger or consolidation",
    ),
    PatternEntry(
        signal="change_of_control",
        pattern=re.compile(r"\bnovat(?:ion|e|ed|ing)\b", re.IGNORECASE),
        confidence=0.78,
        label="Novation clause",
    ),
    PatternEntry(
        signal="change_of_control",
        pattern=re.compile(
            r"\bsuccessor[\s-]*(?:in[\s-]*interest|entity|organization|company)\b",
            re.IGNORECASE,
        ),
        confidence=0.74,
        label="Successor-in-interest reference",
    ),
    PatternEntry(
        signal="change_of_control",
        pattern=re.compile(
            r"\bsubstitution\s+of\s+part(?:y|ies)\b", re.IGNORECASE
        ),
        confidence=0.80,
        label="Substitution of parties",
    ),
    PatternEntry(
        signal="change_of_control",
        pattern=re.compile(
            r"\bsale\s+of\s+(?:all\s+or\s+)?substantially\s+all\s+"
            r"(?:of\s+the\s+)?assets\b",
            re.IGNORECASE,
        ),
        confidence=0.86,
        label="Sale of substantially all assets",
    ),

    # ── assignment_consent ─────────────────────────────────────────────
    PatternEntry(
        signal="assignment_consent",
        pattern=re.compile(
            r"\b(assign(?:ment)?|consent)\b.{0,120}"
            r"\b(transfer|change[\s-]*of[\s-]*control)\b",
            re.IGNORECASE,
        ),
        confidence=0.86,
        label="Assignment/consent linked to transfer",
    ),
    PatternEntry(
        signal="assignment_consent",
        pattern=re.compile(
            r"\bprior\s+written\s+(?:consent|approval)\b.{0,120}"
            r"\b(?:assign|transfer|novat)",
            re.IGNORECASE,
        ),
        confidence=0.88,
        label="Prior written consent for assignment",
    ),
    PatternEntry(
        signal="assignment_consent",
        pattern=re.compile(
            r"\b(?:shall\s+not|may\s+not|cannot|will\s+not)\s+"
            r"(?:assign|transfer|novate|delegate)\b",
            re.IGNORECASE,
        ),
        confidence=0.85,
        label="Assignment prohibition",
    ),
    PatternEntry(
        signal="assignment_consent",
        pattern=re.compile(
            r"\b(?:consent|approval)\s+(?:of|from)\s+(?:the\s+)?(?:other\s+)?"
            r"part(?:y|ies)\b.{0,80}\b(?:assign|transfer|novat)",
            re.IGNORECASE,
        ),
        confidence=0.84,
        label="Party consent required for assignment",
    ),
    PatternEntry(
        signal="assignment_consent",
        pattern=re.compile(r"\banti[\s-]*assignment\b", re.IGNORECASE),
        confidence=0.88,
        label="Anti-assignment provision",
    ),
    PatternEntry(
        signal="assignment_consent",
        pattern=re.compile(
            r"\b(?:assign(?:ment)?|transfer)\b.{0,100}"
            r"\b(?:void|voidable|null\s+and\s+void)\b",
            re.IGNORECASE,
        ),
        confidence=0.86,
        label="Assignment void clause",
    ),

    # ── termination_on_coc ─────────────────────────────────────────────
    PatternEntry(
        signal="termination_on_coc",
        pattern=re.compile(
            r"\btermination\b.{0,120}"
            r"\b(change[\s-]*of[\s-]*control|transfer|assignment)\b",
            re.IGNORECASE,
        ),
        confidence=0.86,
        label="Termination triggered by CoC/transfer",
    ),
    PatternEntry(
        signal="termination_on_coc",
        pattern=re.compile(
            r"\b(?:event\s+of\s+)?default\b.{0,120}"
            r"\b(?:change[\s-]*of[\s-]*control|transfer|assignment)\b",
            re.IGNORECASE,
        ),
        confidence=0.82,
        label="Default event linked to CoC",
    ),
    PatternEntry(
        signal="termination_on_coc",
        pattern=re.compile(
            r"\bmaterial\s+adverse\s+(?:change|effect|event)\b", re.IGNORECASE
        ),
        confidence=0.72,
        label="Material adverse change/effect",
    ),
    PatternEntry(
        signal="termination_on_coc",
        pattern=re.compile(
            r"\b(?:penalt(?:y|ies)|liquidated\s+damages|break(?:age)?\s+fee)\b"
            r".{0,120}\b(?:transfer|assign|terminat)",
            re.IGNORECASE,
        ),
        confidence=0.84,
        label="Penalty/damages on transfer or termination",
    ),
    PatternEntry(
        signal="termination_on_coc",
        pattern=re.compile(
            r"\btermination\s+(?:for\s+)?convenience\b.{0,80}"
            r"\b(?:fee|penalt|payment|cost|charge)\b",
            re.IGNORECASE,
        ),
        confidence=0.78,
        label="Termination for convenience with fee",
    ),
    PatternEntry(
        signal="termination_on_coc",
        pattern=re.compile(
            r"\baccelerat(?:e|ion)\b.{0,100}"
            r"\b(?:change[\s-]*of[\s-]*control|default|terminat)\b",
            re.IGNORECASE,
        ),
        confidence=0.80,
        label="Acceleration on CoC/default",
    ),

    # ── consent_not_required (negative evidence) ───────────────────────
    PatternEntry(
        signal="consent_not_required",
        pattern=re.compile(
            r"\bconsent\s+(?:is\s+)?not\s+required\b", re.IGNORECASE
        ),
        confidence=0.74,
        label="Consent not required",
    ),
    PatternEntry(
        signal="consent_not_required",
        pattern=re.compile(
            r"\bno\s+(?:prior\s+)?consent\s+(?:is\s+)?(?:required|necessary|needed)\b",
            re.IGNORECASE,
        ),
        confidence=0.74,
        label="No consent required/necessary",
    ),
    PatternEntry(
        signal="consent_not_required",
        pattern=re.compile(
            r"\bwithout\s+(?:the\s+)?(?:prior\s+)?(?:written\s+)?(?:consent|approval)\b",
            re.IGNORECASE,
        ),
        confidence=0.72,
        label="Without consent/approval",
    ),
    PatternEntry(
        signal="consent_not_required",
        pattern=re.compile(r"\bfreely\s+assign(?:able)?\b", re.IGNORECASE),
        confidence=0.76,
        label="Freely assignable",
    ),
    PatternEntry(
        signal="consent_not_required",
        pattern=re.compile(
            r"\bno\s+(?:prior\s+)?approval\s+(?:is\s+)?(?:required|necessary|needed)\b",
            re.IGNORECASE,
        ),
        confidence=0.74,
        label="No approval necessary",
    ),
    PatternEntry(
        signal="consent_not_required",
        pattern=re.compile(
            r"\bconsent\s+(?:is\s+)?hereby\s+(?:waived|granted|given)\b", re.IGNORECASE
        ),
        confidence=0.78,
        label="Consent waived or granted",
    ),
    PatternEntry(
        signal="consent_not_required",
        pattern=re.compile(r"\bmay\s+assign\s+without\b", re.IGNORECASE),
        confidence=0.74,
        label="May assign without restriction",
    ),
]

# All known signal groups -- used as keys in _collect_hits output.
SIGNAL_GROUPS: FrozenSet[str] = frozenset(entry.signal for entry in SIGNAL_REGISTRY)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_negation(text: str, match_start: int) -> bool:
    """Check for negation words in a window before the match.

    Conservative: only detects negation, never interprets it.
    Caller decides how to adjust confidence.
    """
    window_start = max(0, match_start - _NEGATION_WINDOW)
    window = text[window_start:match_start]
    return bool(_NEGATION_RE.search(window))


def _make_evidence(
    row: dict,
    start: int,
    end: int,
    signal: str,
    confidence: float,
    *,
    label: str = "",
    negation_detected: bool = False,
) -> dict:
    """Build an evidence dict from a chunk row and match span."""
    text = str(row.get("text") or "")
    left = max(0, start - 120)
    right = min(len(text), end + 120)
    quote = text[left:right].strip().replace("\n", " ")
    if len(quote) > 900:
        quote = quote[:897] + "..."
    return {
        "source_document_id": row.get("document_id"),
        "source_chunk_id": str(row.get("id") or ""),
        "source_page_number": row.get("page_number"),
        "char_start": start,
        "char_end": end,
        "quote": quote,
        "confidence": confidence,
        "metadata_json": {
            "signal": signal,
            "label": label,
            "negation_detected": negation_detected,
            "bbox": row.get("bbox") if isinstance(row.get("bbox"), dict) else None,
            "source_page_range": row.get("page_range") or [],
        },
    }


def _best_evidence_confidence(evidence_list: List[dict]) -> float:
    """Return the highest confidence from an evidence list, or 0.0 if empty."""
    if not evidence_list:
        return 0.0
    return max(float(e.get("confidence") or 0.0) for e in evidence_list)


# ---------------------------------------------------------------------------
# Hit collection
# ---------------------------------------------------------------------------

def _collect_hits(chunks: Sequence[dict]) -> Dict[str, List[dict]]:
    """Scan all chunks against the signal registry.

    Deduplicates per (chunk_id, signal_group): keeps only the highest-
    confidence match when multiple patterns in the same group match the
    same chunk.  Different signal groups can each produce a hit from the
    same chunk (this is correct -- a clause can be both a CoC trigger
    and an assignment restriction).
    """
    hits: Dict[str, List[dict]] = {group: [] for group in SIGNAL_GROUPS}

    for row in chunks:
        text = str(row.get("text") or "")
        if not text:
            continue

        # Best hit per signal group for this chunk.
        best: Dict[str, Tuple[float, dict]] = {}

        for entry in SIGNAL_REGISTRY:
            match = entry.pattern.search(text)
            if not match:
                continue

            start, end = match.span()
            confidence = entry.confidence
            negated = _detect_negation(text, start)
            if negated:
                confidence = round(max(0.0, confidence - _NEGATION_CONFIDENCE_PENALTY), 3)

            prev = best.get(entry.signal)
            if prev is None or confidence > prev[0]:
                best[entry.signal] = (
                    confidence,
                    _make_evidence(
                        row, start, end, entry.signal, confidence,
                        label=entry.label,
                        negation_detected=negated,
                    ),
                )

        for signal, (_, evidence) in best.items():
            hits[signal].append(evidence)

    return hits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_change_of_control_claims(
    chunks: Sequence[dict],
    coverage_metrics: Dict[str, float],
) -> Tuple[List[dict], Dict[str, List[dict]]]:
    """Build deterministic claims for a change-of-control investigation.

    Returns:
        (claims, claim_evidence_map) where claim_evidence_map is keyed
        by claim_key.
    """
    hits = _collect_hits(chunks)

    positive_coc = hits["change_of_control"] + hits["assignment_consent"]
    termination_hits = hits["termination_on_coc"]
    negative_hits = hits["consent_not_required"]

    weak_coverage = str(coverage_metrics.get("coverage_status")) == "weak"
    coverage_score = float(coverage_metrics.get("coverage_score") or 0.0)

    claims: List[dict] = []
    claim_evidence: Dict[str, List[dict]] = {}

    def build_reason_codes(
        *,
        verification_status: str,
        confidence: float,
        evidence: List[dict],
        include_conflict: bool = False,
    ) -> List[str]:
        codes: List[str] = []
        if verification_status == "needs_review" and not evidence:
            codes.append("insufficient_evidence")
        if include_conflict:
            codes.append("conflicting_evidence")
        if confidence >= 0.8 and coverage_score < 0.5:
            codes.append("low_coverage_high_confidence")
        if confidence < 0.6 and coverage_score >= 0.7:
            codes.append("low_confidence_high_coverage")
        # Flag if any evidence had negation detected.
        if any(
            (e.get("metadata_json") or {}).get("negation_detected")
            for e in evidence
        ):
            codes.append("negation_detected_in_evidence")
        return list(dict.fromkeys(codes))

    # ------------------------------------------------------------------
    # Claim A: contracts requiring consent on change-of-control
    # ------------------------------------------------------------------
    claim_a_key = "contracts_require_consent_on_coc"
    if positive_coc:
        stance = "supported"
        confidence = round(min(0.92, max(0.80, _best_evidence_confidence(positive_coc))), 3)
        verification_status = "verified"
        evidence = positive_coc[:5]
    elif negative_hits:
        stance = "contradicted"
        confidence = 0.68
        verification_status = "needs_review"
        evidence = negative_hits[:3]
    else:
        stance = "inconclusive"
        confidence = 0.45
        verification_status = "needs_review"
        evidence = []
    claim_a_reason_codes = build_reason_codes(
        verification_status=verification_status,
        confidence=confidence,
        evidence=evidence,
        include_conflict=bool(positive_coc and negative_hits),
    )
    claims.append(
        {
            "claim_key": claim_a_key,
            "claim_text": "Contracts requiring consent on change-of-control exist.",
            "stance": stance,
            "severity": "high",
            "verification_status": verification_status,
            "confidence": confidence,
            "metadata_json": {
                "version": "coc_claims_v2",
                "decision_reason_codes": claim_a_reason_codes,
                "positive_hit_count": len(positive_coc),
                "negative_hit_count": len(negative_hits),
            },
        }
    )
    claim_evidence[claim_a_key] = evidence

    # ------------------------------------------------------------------
    # Claim B: termination or penalty exposure on change-of-control
    # ------------------------------------------------------------------
    claim_b_key = "termination_penalty_exposure_on_coc"
    if termination_hits:
        stance = "supported"
        confidence = round(min(0.90, max(0.76, _best_evidence_confidence(termination_hits))), 3)
        verification_status = "verified"
        evidence = termination_hits[:5]
    else:
        stance = "inconclusive"
        confidence = 0.41
        verification_status = "needs_review"
        evidence = []
    claim_b_reason_codes = build_reason_codes(
        verification_status=verification_status,
        confidence=confidence,
        evidence=evidence,
    )
    claims.append(
        {
            "claim_key": claim_b_key,
            "claim_text": "Termination or penalty exposure exists on change-of-control.",
            "stance": stance,
            "severity": "high",
            "verification_status": verification_status,
            "confidence": confidence,
            "metadata_json": {
                "version": "coc_claims_v2",
                "decision_reason_codes": claim_b_reason_codes,
                "termination_hit_count": len(termination_hits),
            },
        }
    )
    claim_evidence[claim_b_key] = evidence

    # ------------------------------------------------------------------
    # Claim C: no explicit CoC risk detected (safety-net claim)
    # ------------------------------------------------------------------
    claim_c_key = "no_explicit_coc_risk_detected"
    if not positive_coc and not termination_hits and not weak_coverage:
        stance = "supported"
        confidence = 0.71
        verification_status = "verified"
    elif positive_coc or termination_hits:
        stance = "contradicted"
        confidence = 0.84
        verification_status = "verified"
    else:
        stance = "inconclusive"
        confidence = 0.4
        verification_status = "needs_review"
    claim_c_reason_codes = build_reason_codes(
        verification_status=verification_status,
        confidence=confidence,
        evidence=(negative_hits[:3] if negative_hits else []),
        include_conflict=bool(positive_coc and negative_hits),
    )
    claims.append(
        {
            "claim_key": claim_c_key,
            "claim_text": "No explicit change-of-control risk was found in reviewed evidence.",
            "stance": stance,
            "severity": "medium",
            "verification_status": verification_status,
            "confidence": confidence,
            "metadata_json": {
                "version": "coc_claims_v2",
                "decision_reason_codes": claim_c_reason_codes,
            },
        }
    )
    claim_evidence[claim_c_key] = negative_hits[:3] if negative_hits else []

    # ------------------------------------------------------------------
    # Claim D: coverage insufficient -- needs legal review
    # ------------------------------------------------------------------
    claim_d_key = "coverage_insufficient_needs_legal_review"
    if weak_coverage:
        stance = "supported"
        confidence = 0.9
        verification_status = "needs_review"
    else:
        stance = "contradicted"
        confidence = 0.76
        verification_status = "verified"
    claim_d_reason_codes = build_reason_codes(
        verification_status=verification_status,
        confidence=confidence,
        evidence=[],
    )
    claims.append(
        {
            "claim_key": claim_d_key,
            "claim_text": (
                "Coverage is insufficient; legal review is required "
                "before relying on this conclusion."
            ),
            "stance": stance,
            "severity": "medium",
            "verification_status": verification_status,
            "confidence": confidence,
            "metadata_json": {
                "version": "coc_claims_v2",
                "coverage_status": coverage_metrics.get("coverage_status"),
                "decision_reason_codes": claim_d_reason_codes,
            },
        }
    )
    claim_evidence[claim_d_key] = []

    return claims, claim_evidence
