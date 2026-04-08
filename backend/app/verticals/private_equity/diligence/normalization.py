from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

_ALLOWED_RISK_SEVERITIES = {"high", "medium", "low"}
_ALLOWED_FINDING_SEVERITIES = {"high", "medium", "low"}
_ALLOWED_FINDING_STATUSES = {"open", "resolved", "dismissed"}
_ALLOWED_SUMMARY_READINESS = {"not_ready", "caution", "ready_for_draft"}
_ALLOWED_FINDING_CATEGORIES = {
    "contract",
    "debt",
    "commercial",
    "ip",
    "people",
    "financial",
    "risk",
    "legal",
    "spa",
    "tax",
    "regulatory",
    "privacy",
    "esg",
    "insurance",
    "governance",
    "numeric_reconciliation",
    "missing_clause",
}


def _coerce_str(value: Any, *, default: str = "", max_length: Optional[int] = None) -> str:
    if value is None:
        text = default
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = text.strip()
    if not text:
        text = default
    if max_length is not None:
        text = text[:max_length]
    return text


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _coerce_confidence(value: Any, *, default: float = 0.0) -> float:
    parsed = _coerce_float(value)
    if parsed is None:
        return default
    return max(0.0, min(1.0, parsed))


def _normalize_severity(value: Any, *, default: str = "medium") -> str:
    severity = _coerce_str(value, default=default, max_length=20).lower()
    return severity if severity in _ALLOWED_FINDING_SEVERITIES else default


def _normalize_status(value: Any, *, default: str = "open") -> str:
    status = _coerce_str(value, default=default, max_length=30).lower()
    return status if status in _ALLOWED_FINDING_STATUSES else default


def normalize_text_note(value: Any, *, max_length: int = 500) -> Optional[str]:
    text = _coerce_str(value, max_length=max_length)
    return text or None


def _normalize_category(value: Any, *, default: str = "risk") -> str:
    category = _coerce_str(value, default=default, max_length=120).lower()
    return category if category in _ALLOWED_FINDING_CATEGORIES else default


def _normalize_string_list(items: Any, *, max_items: int = 8, max_length: int = 120) -> List[str]:
    if not isinstance(items, list):
        return []
    normalized: List[str] = []
    seen: set[str] = set()
    for item in items:
        text = _coerce_str(item, max_length=max_length)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= max_items:
            break
    return normalized


def _infer_workflow_owner(category: str) -> str:
    if category in {"tax", "regulatory", "privacy", "legal", "insurance"}:
        return "specialist"
    if category in {"financial", "debt", "numeric_reconciliation"}:
        return "finance"
    if category in {"commercial", "people"}:
        return "deal_team"
    return "legal"


def _infer_workflow_bucket(category: str, severity: str, assessment: Optional[str]) -> str:
    if severity == "high":
        return "ic_blocker"
    if assessment == "flagged" or category in {"tax", "regulatory", "privacy", "legal", "insurance"}:
        return "specialist_review"
    if category == "missing_clause":
        return "diligence_gap"
    if category in {"financial", "debt", "numeric_reconciliation"}:
        return "underwriting_input"
    return "confirmatory_review"


def _default_recommendation(category: str, severity: str, assessment: Optional[str]) -> str:
    if category == "missing_clause":
        return "Request the missing support or confirm the provision is intentionally absent before IC drafting."
    if category == "numeric_reconciliation":
        return "Reconcile metric definitions, periods, and units before using this datapoint in underwriting or IC materials."
    if category in {"financial", "debt"}:
        return "Quantify the exposure in the model and confirm the underlying definition with management."
    if assessment == "flagged" or category in {"tax", "regulatory", "privacy", "legal", "insurance"}:
        return "Escalate to the relevant specialist and confirm remediation, exposure, and closing-condition implications."
    if severity == "high":
        return "Escalate this issue, quantify downside exposure, and confirm whether it should affect IC conditions or pricing."
    return "Confirm the issue against source documents and request targeted backup if it affects diligence conclusions."


def _fallback_evidence_from_finding(finding: Dict[str, Any], metadata_json: Dict[str, Any], confidence: float) -> List[Dict[str, Any]]:
    quote = _coerce_str(finding.get("evidence_quote"), max_length=1000)
    document_id = normalize_text_note(finding.get("source_document_id"), max_length=36)
    page_number = _coerce_int(finding.get("source_page_number"))
    if not quote or not document_id:
        return []
    return [
        {
            "source_document_id": document_id,
            "source_chunk_id": normalize_text_note(finding.get("source_chunk_id"), max_length=120),
            "source_page_number": page_number,
            "char_start": None,
            "char_end": None,
            "quote": quote,
            "confidence": confidence,
            "metadata_json": {
                **(metadata_json or {}),
                "evidence_origin": "finding_fallback",
            },
        }
    ]


def normalize_finding_entry(finding: Any, *, source_kind: str = "pipeline") -> Optional[Dict[str, Any]]:
    if not isinstance(finding, dict):
        return None

    category = _normalize_category(finding.get("category"), default="risk")
    severity = _normalize_severity(finding.get("severity"), default="medium")
    status = _normalize_status(finding.get("status"), default="open")
    confidence = _coerce_confidence(finding.get("confidence"), default=0.0)
    metadata_json = dict(finding.get("metadata_json") or {})
    assessment = normalize_text_note(metadata_json.get("assessment"), max_length=60)
    supporting_evidence = _normalize_string_list(metadata_json.get("supporting_evidence"), max_items=10, max_length=120)

    title = _coerce_str(finding.get("title"), max_length=200)
    description = _coerce_str(finding.get("description"), max_length=1000)
    if not title and not description:
        return None
    if not title:
        title = description[:200]
    if not description:
        description = title

    recommendation = _coerce_str(
        finding.get("recommendation"),
        default=_default_recommendation(category, severity, assessment),
        max_length=500,
    )
    evidence_list = normalize_evidence_records(finding.get("evidence_list") or [])
    if not evidence_list:
        evidence_list = _fallback_evidence_from_finding(finding, metadata_json, confidence)

    workflow_bucket = _infer_workflow_bucket(category, severity, assessment)
    owner_hint = _infer_workflow_owner(category)
    next_step_hint = _default_recommendation(category, severity, assessment)

    normalized = {
        "category": category,
        "severity": severity,
        "title": title,
        "description": description,
        "recommendation": recommendation,
        "status": status,
        "source_document_id": normalize_text_note(finding.get("source_document_id"), max_length=36),
        "source_chunk_id": normalize_text_note(finding.get("source_chunk_id"), max_length=120),
        "source_page_number": _coerce_int(finding.get("source_page_number")),
        "evidence_quote": normalize_text_note(finding.get("evidence_quote"), max_length=300),
        "confidence": confidence,
        "metadata_json": {
            **metadata_json,
            "assessment": assessment,
            "supporting_evidence": supporting_evidence,
            "source_kind": source_kind,
            "workflow": {
                "bucket": workflow_bucket,
                "owner_hint": owner_hint,
                "next_step_hint": next_step_hint,
                "is_ic_relevant": severity in {"high", "medium"} or workflow_bucket in {"ic_blocker", "underwriting_input", "specialist_review"},
            },
        },
        "evidence_list": evidence_list,
    }

    if not normalized["evidence_quote"] and evidence_list:
        normalized["evidence_quote"] = evidence_list[0].get("quote")
    if normalized["source_document_id"] is None and evidence_list:
        normalized["source_document_id"] = evidence_list[0].get("source_document_id")
    if normalized["source_chunk_id"] is None and evidence_list:
        normalized["source_chunk_id"] = evidence_list[0].get("source_chunk_id")
    if normalized["source_page_number"] is None and evidence_list:
        normalized["source_page_number"] = evidence_list[0].get("source_page_number")

    return normalized


def normalize_findings(items: Any, *, source_kind: str = "pipeline", limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    deduped: Dict[tuple, Dict[str, Any]] = {}
    for item in items:
        normalized = normalize_finding_entry(item, source_kind=source_kind)
        if not normalized:
            continue
        key = (
            normalized.get("title"),
            normalized.get("source_document_id"),
            normalized.get("source_page_number"),
            normalized.get("metadata_json", {}).get("engine"),
        )
        existing = deduped.get(key)
        if existing is None or normalized.get("confidence", 0.0) > existing.get("confidence", 0.0):
            deduped[key] = normalized

    findings = list(deduped.values())
    findings.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item.get("severity"), 3),
            0 if item.get("status") == "open" else 1,
            -(item.get("confidence") or 0.0),
            item.get("title") or "",
        )
    )
    return findings[:limit] if limit is not None else findings


def _normalize_historical_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        year = _coerce_str(row.get("year"), max_length=40)
        normalized_row = {
            "year": year or "unknown",
            "revenue": _coerce_float(row.get("revenue")),
            "ebitda": _coerce_float(row.get("ebitda")),
            "ebitda_margin": _coerce_float(row.get("ebitda_margin")),
            "gross_profit": _coerce_float(row.get("gross_profit")),
            "net_income": _coerce_float(row.get("net_income")),
            "capex": _coerce_float(row.get("capex")),
            "free_cash_flow": _coerce_float(row.get("free_cash_flow")),
        }
        has_numeric = any(v is not None for k, v in normalized_row.items() if k != "year")
        if has_numeric:
            normalized.append(normalized_row)
    return normalized[:12]


def _normalize_metric_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metric_name = _coerce_str(row.get("metric_name"), max_length=80)
        if not metric_name:
            continue
        value = _coerce_float(row.get("value"))
        raw_quote = normalize_text_note(row.get("raw_quote"), max_length=500)
        if value is None and not raw_quote:
            continue
        normalized.append(
            {
                "metric_name": metric_name,
                "value": value,
                "unit": normalize_text_note(row.get("unit"), max_length=20),
                "period": normalize_text_note(row.get("period"), max_length=40),
                "definition": normalize_text_note(row.get("definition"), max_length=120),
                "raw_quote": raw_quote,
                "confidence": _coerce_confidence(row.get("confidence"), default=0.0),
            }
        )
    return normalized[:20]


def normalize_llm_financials(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    normalized = {
        "currency": _coerce_str(raw.get("currency"), default="USD", max_length=10).upper() or "USD",
        "historical": _normalize_historical_rows(raw.get("historical")),
        "ratios": _normalize_metric_rows(raw.get("ratios")),
        "other_metrics": _normalize_metric_rows(raw.get("other_metrics")),
        "data_quality_notes": normalize_text_note(raw.get("data_quality_notes"), max_length=500),
    }

    if not (
        normalized["historical"]
        or normalized["ratios"]
        or normalized["other_metrics"]
        or normalized["data_quality_notes"]
    ):
        return None
    return normalized


def normalize_priority_risks(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _coerce_str(item.get("title"), max_length=160)
        reasoning = _coerce_str(item.get("reasoning"), max_length=500)
        if not title or not reasoning:
            continue
        severity = _normalize_severity(item.get("severity"), default="medium")
        normalized.append({"title": title, "reasoning": reasoning, "severity": severity})
    return normalized[:5]


def normalize_management_questions(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question = _coerce_str(item.get("question"), max_length=300)
        rationale = _coerce_str(item.get("rationale"), max_length=400)
        if not question:
            continue
        normalized.append(
            {
                "question": question,
                "rationale": rationale,
                "related_finding": normalize_text_note(item.get("related_finding"), max_length=120),
            }
        )
    return normalized[:7]


def normalize_citations(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    citations: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entity = _coerce_str(item.get("entity"), max_length=255)
        quote = _coerce_str(item.get("quote"), max_length=220)
        page_number = _coerce_int(item.get("page_number"))
        document_id = normalize_text_note(item.get("document_id"), max_length=36)
        if not entity and not quote and not document_id:
            continue
        citations.append(
            {
                "entity": entity or "Supporting evidence",
                "document_id": document_id,
                "page_number": page_number,
                "quote": quote,
                "confidence": _coerce_confidence(item.get("confidence"), default=0.0),
            }
        )
    return citations[:10]


def normalize_evidence_records(items: Iterable[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        quote = _coerce_str(item.get("quote"), max_length=2000)
        if not quote:
            continue
        normalized.append(
            {
                "source_document_id": normalize_text_note(item.get("source_document_id"), max_length=36),
                "source_chunk_id": normalize_text_note(item.get("source_chunk_id"), max_length=120),
                "source_page_number": _coerce_int(item.get("source_page_number")),
                "char_start": _coerce_int(item.get("char_start")),
                "char_end": _coerce_int(item.get("char_end")),
                "quote": quote,
                "confidence": _coerce_confidence(item.get("confidence"), default=0.0),
                "metadata_json": item.get("metadata_json") if isinstance(item.get("metadata_json"), dict) else None,
            }
        )
    return normalized


def normalize_summary_metadata(metadata: Any) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    normalized = dict(metadata)
    if "top_risks" in normalized:
        top_risks: List[Dict[str, Any]] = []
        for item in normalized.get("top_risks") or []:
            if not isinstance(item, dict):
                continue
            title = _coerce_str(item.get("title"), max_length=160)
            summary = _coerce_str(item.get("summary") or item.get("reasoning"), max_length=500)
            if not title and not summary:
                continue
            top_risks.append(
                {
                    **item,
                    "title": title or "Priority risk",
                    "summary": summary,
                    "severity": _normalize_severity(item.get("severity"), default="medium"),
                    "status": _normalize_status(item.get("status"), default="open"),
                    "confidence": _coerce_confidence(item.get("confidence"), default=0.0),
                }
            )
        normalized["top_risks"] = top_risks[:5]
    if "management_questions" in normalized:
        normalized["management_questions"] = normalize_management_questions(normalized.get("management_questions"))
    if "valuation_signals" in normalized and not isinstance(normalized.get("valuation_signals"), list):
        normalized["valuation_signals"] = []
    if "contradictions" in normalized and not isinstance(normalized.get("contradictions"), list):
        normalized["contradictions"] = []
    if "deal_blockers" in normalized and not isinstance(normalized.get("deal_blockers"), list):
        normalized["deal_blockers"] = []
    if "document_gap_register" in normalized and not isinstance(normalized.get("document_gap_register"), list):
        normalized["document_gap_register"] = []
    if "ic_readiness" in normalized and isinstance(normalized.get("ic_readiness"), dict):
        status = _coerce_str(normalized["ic_readiness"].get("status"), default="caution", max_length=30).lower()
        normalized["ic_readiness"] = {
            **normalized["ic_readiness"],
            "status": status if status in _ALLOWED_SUMMARY_READINESS else "caution",
            "headline": _coerce_str(normalized["ic_readiness"].get("headline"), default="Use with caution", max_length=160),
            "recommended_next_step": _coerce_str(normalized["ic_readiness"].get("recommended_next_step"), default="Review the output before downstream use.", max_length=300),
            "blocker_count": _coerce_int(normalized["ic_readiness"].get("blocker_count")) or 0,
            "required_gap_count": _coerce_int(normalized["ic_readiness"].get("required_gap_count")) or 0,
            "verification_review_count": _coerce_int(normalized["ic_readiness"].get("verification_review_count")) or 0,
            "classification_review_count": _coerce_int(normalized["ic_readiness"].get("classification_review_count")) or 0,
        }
    if "data_quality_assessment" in normalized:
        normalized["data_quality_assessment"] = normalize_text_note(normalized.get("data_quality_assessment"), max_length=500)
    return normalized


def normalize_summary_payload(payload: Any, *, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fallback = fallback or {}
    payload = payload if isinstance(payload, dict) else {}

    markdown = _coerce_str(payload.get("markdown"), default=_coerce_str(fallback.get("markdown"), default="# Diligence Overview"))
    metadata = normalize_summary_metadata({**(fallback.get("metadata") or {}), **(payload.get("metadata") or {})})
    citations = normalize_citations(payload.get("citations") if payload.get("citations") is not None else fallback.get("citations"))
    evidence_list = normalize_evidence_records(payload.get("evidence_list") if payload.get("evidence_list") is not None else fallback.get("evidence_list") or [])

    return {
        "markdown": markdown,
        "citations": citations,
        "confidence": _coerce_confidence(payload.get("confidence"), default=0.0),
        "evidence_list": evidence_list,
        "metadata": metadata,
    }
