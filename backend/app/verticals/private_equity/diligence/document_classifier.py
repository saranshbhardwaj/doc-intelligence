"""Document type classification for PE diligence."""
from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Dict, List

from app.verticals.private_equity.diligence.doc_types import (
    DEFAULT_DOC_TYPE,
    DOC_TYPE_METADATA,
    GENERIC_DOC_TYPES,
    is_generic_doc_type,
)


_FILENAME_WEIGHT = 3.0
_TITLE_WEIGHT = 2.0
_BODY_WEIGHT = 1.0
_MIN_SPECIFIC_SCORE = 1.5
_LOW_MARGIN_THRESHOLD = 1.25
_LOW_SIGNAL_THRESHOLD = 2.5


def _build_rule_anchor_id(*, document_id: str, document_type: str, signals: List[str]) -> str:
    signals_key = "|".join(sorted([str(signal).strip().lower() for signal in signals if signal]))
    digest = hashlib.sha1(signals_key.encode("utf-8")).hexdigest()[:12] if signals_key else "no_signals"
    return f"rule:doc_classifier_v2:{document_id}:{document_type}:{digest}"


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


def _build_scorecards(text: str, filename: str) -> tuple[dict[str, float], dict[str, List[str]]]:
    filename_hay = str(filename or "").lower()
    body_hay = str(text or "").lower()
    title_hay = body_hay[:2500]

    scores: dict[str, float] = {}
    matched: dict[str, List[str]] = {}

    for doc_type, metadata in DOC_TYPE_METADATA.items():
        type_score = 0.0
        type_hits: List[str] = []
        for pattern in metadata.get("patterns", ()):
            pattern_score = 0.0
            if pattern in filename_hay:
                pattern_score += _FILENAME_WEIGHT
            if pattern in title_hay:
                pattern_score += _TITLE_WEIGHT
            elif pattern in body_hay:
                pattern_score += _BODY_WEIGHT
            if pattern_score > 0:
                type_hits.append(pattern)
                type_score += pattern_score
        scores[doc_type] = round(type_score * float(metadata.get("type_weight", 1.0)), 3)
        matched[doc_type] = type_hits

    return scores, matched


def _confidence_from_scores(top_score: float, second_score: float, *, generic: bool) -> float:
    if generic:
        return 0.58 if top_score > 0 else 0.45
    margin = max(0.0, top_score - second_score)
    confidence = 0.52 + min(0.26, top_score * 0.07) + min(0.17, margin * 0.08)
    return round(min(0.94, confidence), 3)


def _score_doc(text: str, filename: str) -> dict:
    scores, matched = _build_scorecards(text=text, filename=filename)
    specific_scores = {
        doc_type: score
        for doc_type, score in scores.items()
        if doc_type not in GENERIC_DOC_TYPES
    }
    generic_scores = {
        doc_type: score
        for doc_type, score in scores.items()
        if doc_type in GENERIC_DOC_TYPES
    }

    ranked_specific = sorted(specific_scores.items(), key=lambda item: (-item[1], item[0]))
    top_specific_type = ranked_specific[0][0] if ranked_specific else DEFAULT_DOC_TYPE
    top_specific_score = ranked_specific[0][1] if ranked_specific else 0.0
    second_specific_score = ranked_specific[1][1] if len(ranked_specific) > 1 else 0.0

    legal_contract_score = generic_scores.get("legal_contract", 0.0)

    if top_specific_score >= _MIN_SPECIFIC_SCORE:
        document_type = top_specific_type
        top_score = top_specific_score
        second_score = second_specific_score
    elif legal_contract_score > 0:
        document_type = "legal_contract"
        top_score = legal_contract_score
        second_score = top_specific_score
    else:
        document_type = DEFAULT_DOC_TYPE
        top_score = 0.0
        second_score = top_specific_score

    decision_reason_codes: List[str] = []
    if document_type == DEFAULT_DOC_TYPE:
        decision_reason_codes.append("no_pattern_match")
    if document_type == "legal_contract":
        decision_reason_codes.append("generic_fallback")
    if top_score > 0 and (top_score - second_score) < _LOW_MARGIN_THRESHOLD:
        decision_reason_codes.append("low_margin")
    if top_score <= _LOW_SIGNAL_THRESHOLD:
        decision_reason_codes.append("low_signal_strength")

    needs_review = bool(
        is_generic_doc_type(document_type)
        or "low_margin" in decision_reason_codes
        or "low_signal_strength" in decision_reason_codes
        or "no_pattern_match" in decision_reason_codes
    )

    return {
        "document_type": document_type,
        "confidence": _confidence_from_scores(
            top_score,
            second_score,
            generic=is_generic_doc_type(document_type),
        ),
        "needs_review": needs_review,
        "signals": matched.get(document_type, [])[:6],
        "decision_reason_codes": decision_reason_codes,
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
            document_type=str(scored.get("document_type") or DEFAULT_DOC_TYPE),
            signals=[str(signal) for signal in (scored.get("signals") or [])],
        )
        scored["decision_reason_codes"] = [str(code) for code in (scored.get("decision_reason_codes") or [])]
        scored["interpretation_version"] = "rules_v2"
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

    review_doc_ids = [
        doc_id
        for doc_id, item in classifications.items()
        if item.get("needs_review") or is_generic_doc_type(item.get("document_type"))
    ]

    out = []
    for doc_id in review_doc_ids:
        text = _build_doc_text(by_doc_rows.get(doc_id, []), max_chars=max_chars_per_doc)
        item = classifications.get(doc_id, {})
        out.append(
            {
                "document_id": doc_id,
                "filename": by_doc_filename.get(doc_id, ""),
                "text": text,
                "rule_anchor_id": item.get("rule_anchor_id"),
                "rule_document_type": item.get("document_type") or DEFAULT_DOC_TYPE,
                "rule_confidence": item.get("confidence") or 0.0,
                "rule_signals": item.get("signals") or [],
                "decision_reason_codes": item.get("decision_reason_codes") or [],
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
        base_row.setdefault("adjudication_source", "rules_v2")
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
        base_row["interpretation_version"] = "llm_fallback_v2"

        if not candidate_anchor_id or candidate_anchor_id != expected_anchor_id:
            reason_code = "missing_rule_anchor" if not candidate_anchor_id else "anchor_mismatch"
            base_row["needs_review"] = True
            base_row["adjudication_source"] = "rules_v2"
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
                "adjudication_source": "llm_fallback_v2",
                "rule_anchor_id": candidate_anchor_id,
                "decision_reason_codes": [
                    str(code)
                    for code in (base_row.get("decision_reason_codes") or [])
                    if str(code) not in {"missing_rule_anchor", "generic_fallback", "low_margin", "low_signal_strength"}
                ],
            }
            continue

        merged[doc_id] = base_row

    return merged, rejected_candidates
