"""Document type classification for PE diligence."""
from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Dict, List


TYPE_PATTERNS = {
    "amendment": [
        "amendment",
        "first amendment",
        "second amendment",
        "third amendment",
        "amended and restated",
        "addendum",
        "side letter",
        "modification agreement",
        "supplement",
        "joinder",
        "restatement",
        "amendment no",
        "amendment number",
    ],
    "offering_memorandum": [
        "offering memorandum",
        "investment highlights",
        "executive summary",
        "property overview",
    ],
    "purchase_agreement": [
        "purchase agreement",
        "asset purchase",
        "stock purchase",
        "seller",
        "buyer",
        "representations and warranties",
    ],
    "financial_statement": [
        "balance sheet",
        "income statement",
        "cash flow",
        "statement of operations",
        "audited financial statements",
    ],
    "qoe_report": [
        "quality of earnings",
        "qoe",
        "adjusted ebitda",
        "normalization",
    ],
    "legal_contract": [
        "agreement",
        "term and termination",
        "governing law",
        "indemnification",
    ],
}


def _build_rule_anchor_id(*, document_id: str, document_type: str, signals: List[str]) -> str:
    signals_key = "|".join(sorted([str(signal).strip().lower() for signal in signals if signal]))
    digest = hashlib.sha1(signals_key.encode("utf-8")).hexdigest()[:12] if signals_key else "no_signals"
    return f"rule:doc_classifier_v1:{document_id}:{document_type}:{digest}"

def _chunk_order_key(row: dict, fallback_index: int) -> tuple:
    chunk_index = row.get("chunk_index")
    if isinstance(chunk_index, int):
        return (0, chunk_index, fallback_index)
    try:
        if chunk_index is not None:
            return (0, int(chunk_index), fallback_index)
    except Exception:
        pass
    return (1, fallback_index, fallback_index)


def _build_doc_text(doc_rows: List[dict], max_chars: int) -> str:
    ordered = sorted(
        enumerate(doc_rows),
        key=lambda pair: _chunk_order_key(pair[1], pair[0]),
    )
    chunks = [str(row.get("text") or "") for _, row in ordered if row.get("text")]
    stitched_text = "\n".join(chunks)

    if len(stitched_text) <= max_chars:
        return stitched_text

    # Prefer beginning and ending signals while keeping a middle sample.
    # Typical split: 45% head, 20% middle, 35% tail.
    sep = "\n...\n"
    sep_total = len(sep) * 2
    available = max(0, max_chars - sep_total)
    if available <= 0:
        return stitched_text[:max_chars]

    head_budget = int(available * 0.45)
    middle_budget = int(available * 0.20)
    tail_budget = available - head_budget - middle_budget

    head = stitched_text[:head_budget]
    tail = stitched_text[-tail_budget:] if tail_budget > 0 else ""

    middle = ""
    if middle_budget > 0:
        total_len = len(stitched_text)
        middle_start = max(0, (total_len // 2) - (middle_budget // 2))
        middle_end = middle_start + middle_budget
        middle = stitched_text[middle_start:middle_end]

    sampled = f"{head}{sep}{middle}{sep}{tail}" if middle else f"{head}{sep}{tail}"
    return sampled[:max_chars]


def _score_doc(text: str, filename: str) -> dict:
    hay = f"{filename}\n{text}".lower()
    scores = {}
    matched = {}
    for doc_type, patterns in TYPE_PATTERNS.items():
        hits = [p for p in patterns if p in hay]
        matched[doc_type] = hits
        scores[doc_type] = len(hits)

    top_type = max(scores, key=scores.get) if scores else "other"
    top_score = scores.get(top_type, 0)

    if top_score <= 0:
        return {
            "document_type": "other",
            "confidence": 0.45,
            "needs_review": True,
            "signals": [],
        }

    confidence = min(0.95, 0.55 + (top_score * 0.12))
    return {
        "document_type": top_type,
        "confidence": round(confidence, 3),
        "needs_review": confidence < 0.72,
        "signals": matched.get(top_type, [])[:6],
    }


def classify_documents(rows: List[dict]) -> Dict[str, dict]:
    """Classify document type using chunk text and filename signals."""
    by_doc_rows = defaultdict(list)
    by_doc_filename = {}

    for row in rows:
        doc_id = row.get("document_id")
        if not doc_id:
            continue
        by_doc_rows[doc_id].append(row)
        if row.get("filename") and doc_id not in by_doc_filename:
            by_doc_filename[doc_id] = row.get("filename") or ""

    out = {}
    all_doc_ids = set(by_doc_rows.keys()) | set(by_doc_filename.keys())
    for doc_id in all_doc_ids:
        text = _build_doc_text(by_doc_rows.get(doc_id, []), max_chars=12000)
        filename = by_doc_filename.get(doc_id, "")
        scored = _score_doc(text=text, filename=filename)
        scored["rule_anchor_id"] = _build_rule_anchor_id(
            document_id=doc_id,
            document_type=str(scored.get("document_type") or "other"),
            signals=[str(signal) for signal in (scored.get("signals") or [])],
        )
        scored["decision_reason_codes"] = [str(code) for code in (scored.get("decision_reason_codes") or [])]
        scored["interpretation_version"] = "rules_v1"
        out[doc_id] = scored
    return out


def build_low_confidence_inputs(
    rows: List[dict],
    classifications: Dict[str, dict],
    *,
    max_chars_per_doc: int = 4000,
) -> List[dict]:
    by_doc_rows = defaultdict(list)
    by_doc_filename = {}

    for row in rows:
        doc_id = row.get("document_id")
        if not doc_id:
            continue
        by_doc_rows[doc_id].append(row)
        if row.get("filename") and doc_id not in by_doc_filename:
            by_doc_filename[doc_id] = row.get("filename") or ""

    low_confidence_doc_ids = [
        doc_id
        for doc_id, item in classifications.items()
        if item.get("needs_review")
    ]

    out = []
    for doc_id in low_confidence_doc_ids:
        text = _build_doc_text(by_doc_rows.get(doc_id, []), max_chars=max_chars_per_doc)
        item = classifications.get(doc_id, {})
        out.append(
            {
                "document_id": doc_id,
                "filename": by_doc_filename.get(doc_id, ""),
                "text": text,
                "rule_anchor_id": item.get("rule_anchor_id"),
                "rule_document_type": item.get("document_type") or "other",
                "rule_confidence": item.get("confidence") or 0.0,
                "rule_signals": item.get("signals") or [],
            }
        )
    return out


def apply_llm_fallback(
    classifications: Dict[str, dict],
    llm_candidates: Dict[str, dict],
    *,
    min_override_confidence: float,
) -> tuple[Dict[str, dict], List[dict]]:
    merged: Dict[str, dict] = {}
    rejected_candidates: List[dict] = []

    for doc_id, base in classifications.items():
        base_row = dict(base)
        base_row.setdefault("adjudication_source", "rules_v1")
        base_row.setdefault("decision_reason_codes", [])
        candidate = llm_candidates.get(doc_id)

        if not candidate:
            merged[doc_id] = base_row
            continue

        llm_confidence = float(candidate.get("confidence") or 0.0)
        expected_anchor_id = str(base_row.get("rule_anchor_id") or "").strip()
        candidate_anchor_id = str(candidate.get("rule_anchor_id") or "").strip()
        base_row["llm_candidate"] = candidate
        base_row["rule_document_type"] = base.get("document_type")
        base_row["rule_confidence"] = base.get("confidence")
        base_row["interpretation_version"] = "llm_fallback_v1"

        if not candidate_anchor_id or candidate_anchor_id != expected_anchor_id:
            reason_code = "missing_rule_anchor" if not candidate_anchor_id else "anchor_mismatch"
            base_row["needs_review"] = True
            base_row["adjudication_source"] = "rules_v1"
            decision_reason_codes = [str(code) for code in (base_row.get("decision_reason_codes") or [])]
            if reason_code not in decision_reason_codes:
                decision_reason_codes.append(reason_code)
            base_row["decision_reason_codes"] = decision_reason_codes
            rejected_candidates.append(
                {
                    "document_id": doc_id,
                    "reason_code": reason_code,
                    "expected_rule_anchor_id": expected_anchor_id,
                    "candidate_rule_anchor_id": candidate_anchor_id,
                    "candidate_confidence": llm_confidence,
                }
            )
            merged[doc_id] = base_row
            continue

        if llm_confidence >= min_override_confidence and candidate.get("document_type"):
            merged[doc_id] = {
                **base_row,
                "document_type": candidate.get("document_type"),
                "confidence": round(max(llm_confidence, float(base.get("confidence") or 0.0)), 3),
                "needs_review": llm_confidence < 0.9,
                "signals": (candidate.get("signals") or base.get("signals") or [])[:6],
                "adjudication_source": "llm_fallback_v1",
                "rule_anchor_id": candidate_anchor_id,
                "decision_reason_codes": [
                    str(code) for code in (base_row.get("decision_reason_codes") or []) if str(code) != "missing_rule_anchor"
                ],
            }
            continue

        merged[doc_id] = base_row

    return merged, rejected_candidates
