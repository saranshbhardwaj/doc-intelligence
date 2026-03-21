"""Checklist, findings, and summary builders for PE diligence analysis."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.verticals.private_equity.diligence.doc_types import DEFAULT_DOC_TYPE, DOC_TYPE_METADATA, PEDocumentType
from app.verticals.private_equity.diligence.normalization import normalize_findings, normalize_summary_payload
from app.verticals.private_equity.diligence.rules import (
    CHECKLIST_RULES,
    CHECKLIST_TEMPLATE,
    CLAUSE_META,
    EXPECTED_CLAUSES_BY_DOC_TYPE,
)
from app.verticals.private_equity.diligence.signals import clip_quote, make_evidence


def build_checklist(
    rows: List[dict],
    clause_hits: List[dict],
    numeric_signals: Dict[str, List[dict]],
    document_classifications: Optional[Dict[str, dict]] = None,
    llm_financials: Optional[dict] = None,
    structured_clauses_by_type: Optional[Dict[str, List[dict]]] = None,
) -> List[dict]:
    by_doc: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        by_doc[row["document_id"]].append(row)

    found_clause_types: set = {h["clause_type"] for h in clause_hits}
    if structured_clauses_by_type:
        found_clause_types.update(structured_clauses_by_type.keys())

    doc_types_present: set = set()
    if document_classifications:
        for cls in document_classifications.values():
            dt = cls.get("document_type")
            if dt:
                doc_types_present.add(dt)

    checklist_entries = []
    for template in CHECKLIST_TEMPLATE:
        key = template["item_key"]
        rules = CHECKLIST_RULES.get(key, {})
        status = "missing"
        confidence = 0.35
        matched_document_id = None
        matched_chunk_id = None
        matched_page_number = None
        evidence_quote = None
        evidence_list: List[dict] = []

        matching_clause_types = [ct for ct in (rules.get("clause_types") or []) if ct in found_clause_types]
        if matching_clause_types:
            hit = next((h for h in clause_hits if h["clause_type"] == matching_clause_types[0]), None)
            if hit:
                ev = hit["evidence"]
                status = "covered"
                confidence = rules.get("base_confidence", 0.80)
                matched_document_id = ev["source_document_id"]
                matched_chunk_id = ev["source_chunk_id"]
                matched_page_number = ev["source_page_number"]
                evidence_quote = ev["quote"]
                evidence_list = [ev]

        if status == "missing":
            for metric in (rules.get("numeric_metrics") or []):
                if numeric_signals.get(metric):
                    ev = numeric_signals[metric][0]["evidence"]
                    status = "covered"
                    confidence = rules.get("base_confidence", 0.80)
                    matched_document_id = ev["source_document_id"]
                    matched_chunk_id = ev["source_chunk_id"]
                    matched_page_number = ev["source_page_number"]
                    evidence_quote = ev["quote"]
                    evidence_list = [ev]
                    break

        if status == "missing":
            for doc_type in (rules.get("doc_types") or []):
                if doc_type in doc_types_present and document_classifications:
                    doc_id = next(
                        (did for did, cls in document_classifications.items() if cls.get("document_type") == doc_type),
                        None,
                    )
                    if doc_id:
                        status = "covered"
                        confidence = rules.get("base_confidence", 0.75)
                        matched_document_id = doc_id
                        break

        if status == "missing" and rules.get("check_llm_financials") and llm_financials:
            if llm_financials.get("historical") or llm_financials.get("ratios"):
                status = "covered"
                confidence = rules.get("base_confidence", 0.82)

        if status == "missing":
            full_keywords = rules.get("keywords") or []
            partial_keywords = rules.get("partial_keywords") or []
            for doc_id, chunk_rows in by_doc.items():
                for row in chunk_rows:
                    text_lower = row["text_lower"]
                    matched_kw = next((kw for kw in full_keywords if kw in text_lower), None)
                    if matched_kw:
                        idx = text_lower.find(matched_kw)
                        ev = make_evidence(
                            row=row,
                            start=idx,
                            end=idx + len(matched_kw),
                            quote=clip_quote(row["text"], idx, idx + len(matched_kw)),
                            confidence=rules.get("base_confidence", 0.72),
                            metadata={"engine": "keyword_v1"},
                        )
                        status = "covered"
                        confidence = rules.get("base_confidence", 0.72)
                        matched_document_id = doc_id
                        matched_chunk_id = row["chunk_id"]
                        matched_page_number = row["page_number"]
                        evidence_quote = ev["quote"]
                        evidence_list = [ev]
                        break
                    if not full_keywords and partial_keywords:
                        matched_pkw = next((kw for kw in partial_keywords if kw in text_lower), None)
                        if matched_pkw:
                            idx = text_lower.find(matched_pkw)
                            ev = make_evidence(
                                row=row,
                                start=idx,
                                end=idx + len(matched_pkw),
                                quote=clip_quote(row["text"], idx, idx + len(matched_pkw)),
                                confidence=max(0.55, rules.get("base_confidence", 0.68) - 0.10),
                                metadata={"engine": "keyword_v1"},
                            )
                            status = "partial"
                            confidence = max(0.55, rules.get("base_confidence", 0.68) - 0.10)
                            matched_document_id = doc_id
                            matched_chunk_id = row["chunk_id"]
                            matched_page_number = row["page_number"]
                            evidence_quote = ev["quote"]
                            evidence_list = [ev]
                            break
                if status != "missing":
                    break

        checklist_entries.append(
            {
                "item": {
                    **template,
                    "status": status,
                    "matched_document_id": matched_document_id,
                    "matched_chunk_id": matched_chunk_id,
                    "matched_page_number": matched_page_number,
                    "evidence_quote": evidence_quote,
                    "confidence": confidence,
                    "metadata_json": {"engine": "checklist_v3"},
                },
                "evidence": evidence_list,
            }
        )
    return checklist_entries


def enrich_finding_from_structured_clause(
    finding: dict,
    structured_clauses_by_type: Dict[str, List[dict]],
) -> dict:
    clause_type = (finding.get("metadata_json") or {}).get("clause_type")
    if not clause_type:
        return finding
    clauses = structured_clauses_by_type.get(clause_type, [])
    if not clauses:
        return finding

    best = clauses[0]
    fields = best.get("extracted_fields") or {}
    enrichments = []
    if fields.get("cap_amount"):
        enrichments.append(f"Cap: ${fields['cap_amount']:,.0f}")
    if fields.get("cap_pct_ev"):
        enrichments.append(f"Cap: {fields['cap_pct_ev']}% of EV")
    if fields.get("survival_months"):
        enrichments.append(f"Survival: {fields['survival_months']}mo")
    if fields.get("basket_amount"):
        bt = fields.get("basket_type") or ""
        enrichments.append(f"Basket: ${fields['basket_amount']:,.0f}" + (f" ({bt})" if bt else ""))
    if fields.get("earnout_metric"):
        period = fields.get("earnout_period_months", "?")
        enrichments.append(f"Earnout: {period}mo on {fields['earnout_metric']}")
    if fields.get("mac_carveouts"):
        enrichments.append(f"MAC carveouts: {', '.join(fields['mac_carveouts'][:3])}")
    if fields.get("adjustment_mechanism"):
        enrichments.append(f"Price adj: {fields['adjustment_mechanism']}")
    if fields.get("threshold"):
        enrichments.append(f"Threshold: {fields['threshold']}")
    if fields.get("consent_required") is True and fields.get("consent_parties"):
        enrichments.append(f"Consent: {', '.join(fields['consent_parties'][:3])}")
    if fields.get("consequences"):
        enrichments.append(f"Consequence: {str(fields['consequences'])[:80]}")
    if fields.get("termination_notice_days"):
        enrichments.append(f"Notice: {fields['termination_notice_days']}d")
    if fields.get("prepayment_penalty_pct"):
        enrichments.append(f"Penalty: {fields['prepayment_penalty_pct']}%")
    if fields.get("threshold_value") is not None and fields.get("threshold_unit"):
        enrichments.append(f"Threshold: {fields['threshold_value']}{fields['threshold_unit']}")
    if fields.get("cure_period_days"):
        enrichments.append(f"Cure: {fields['cure_period_days']}d")
    if not enrichments:
        return finding

    finding = {**finding}
    finding["description"] = finding["description"] + " | " + " · ".join(enrichments)
    interpretation = best.get("interpretation")
    if interpretation:
        finding["metadata_json"] = {**finding.get("metadata_json", {}), "llm_interpretation": interpretation}
    return finding


def detect_missing_clauses(
    clause_hits: List[dict],
    document_classifications: Dict[str, dict],
    rows: List[dict],
) -> List[dict]:
    found_by_doc: Dict[str, set] = defaultdict(set)
    for hit in clause_hits:
        doc_id = hit["evidence"]["source_document_id"]
        found_by_doc[doc_id].add(hit["clause_type"])

    doc_filenames: Dict[str, str] = {}
    for row in rows:
        doc_filenames.setdefault(row["document_id"], row.get("filename", ""))

    missing_findings: List[dict] = []
    for doc_id, cls in document_classifications.items():
        doc_type = cls.get("document_type")
        expected = EXPECTED_CLAUSES_BY_DOC_TYPE.get(doc_type, [])
        if not expected:
            continue
        found = found_by_doc.get(doc_id, set())
        filename = doc_filenames.get(doc_id) or cls.get("filename", doc_id[:8])

        for clause_type, label, severity in expected:
            if clause_type not in found:
                missing_findings.append(
                    {
                        "category": "missing_clause",
                        "severity": severity,
                        "title": f"Missing: {label} not detected in {filename}",
                        "description": (
                            f"Expected '{label}' clause was not detected in '{filename}' "
                            f"(classified as {doc_type.replace('_', ' ')}). "
                            f"This clause is standard in {doc_type.replace('_', ' ')} documents. "
                            "This may indicate the clause exists under a non-standard heading — review manually."
                        ),
                        "recommendation": (
                            f"Locate the {label} provision in the document or request it from the counterparty. "
                            "Confirm it is not present under an alternative heading."
                        ),
                        "status": "open",
                        "source_document_id": doc_id,
                        "source_chunk_id": None,
                        "source_page_number": None,
                        "evidence_quote": None,
                        "confidence": 0.72,
                        "metadata_json": {
                            "engine": "missing_clause_v1",
                            "clause_type": clause_type,
                            "doc_type": doc_type,
                        },
                        "evidence_list": [],
                    }
                )
    return missing_findings


def build_checklist_v2(
    per_doc_findings: List[dict],
    numeric_signals: Dict[str, List[dict]],
    document_classifications: Optional[Dict[str, dict]],
    llm_financials: Optional[dict] = None,
) -> List[dict]:
    doc_types_present: set = set()
    doc_by_type: dict = {}
    if document_classifications:
        for doc_id, cls in document_classifications.items():
            dt = cls.get("document_type")
            if dt:
                doc_types_present.add(dt)
                doc_by_type.setdefault(dt, []).append(doc_id)

    keyword_to_findings: dict = {}
    finding_by_idx: List[dict] = []
    for i, finding in enumerate(per_doc_findings):
        finding_by_idx.append(finding)
        combined = f"{finding.get('title', '')} {finding.get('description', '')}".lower()
        for word in combined.split():
            keyword_to_findings.setdefault(word, []).append(i)

    def _finding_matches(keywords: List[str]) -> Optional[dict]:
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in keyword_to_findings:
                return finding_by_idx[keyword_to_findings[kw_lower][0]]
            for finding in finding_by_idx:
                combined = f"{finding.get('title', '')} {finding.get('description', '')}".lower()
                if kw_lower in combined:
                    return finding
        return None

    checklist_entries = []
    for template in CHECKLIST_TEMPLATE:
        key = template["item_key"]
        rules = CHECKLIST_RULES.get(key, {})
        status = "missing"
        confidence = 0.35
        matched_document_id = None
        evidence_quote = None
        evidence_list: List[dict] = []

        all_keywords = (rules.get("clause_types") or []) + (rules.get("keywords") or []) + (rules.get("partial_keywords") or [])
        match = _finding_matches(all_keywords)
        if match:
            status = "covered"
            confidence = rules.get("base_confidence", 0.78)
            matched_document_id = match.get("source_document_id")
            evidence_quote = (match.get("evidence_quote") or match.get("title") or "")[:200]

        if status == "missing":
            for metric in (rules.get("numeric_metrics") or []):
                if numeric_signals.get(metric):
                    ev = numeric_signals[metric][0]["evidence"]
                    status = "covered"
                    confidence = rules.get("base_confidence", 0.80)
                    matched_document_id = ev["source_document_id"]
                    evidence_quote = ev["quote"]
                    evidence_list = [ev]
                    break

        if status == "missing":
            for doc_type in (rules.get("doc_types") or []):
                if doc_type in doc_types_present:
                    doc_ids = doc_by_type.get(doc_type, [])
                    if doc_ids:
                        status = "covered"
                        confidence = rules.get("base_confidence", 0.75)
                        matched_document_id = doc_ids[0]
                        break

        if status == "missing" and rules.get("check_llm_financials") and llm_financials:
            if llm_financials.get("historical") or llm_financials.get("ratios"):
                status = "covered"
                confidence = rules.get("base_confidence", 0.82)

        checklist_entries.append(
            {
                "item": {
                    **template,
                    "status": status,
                    "confidence": confidence,
                    "matched_document_id": matched_document_id,
                    "matched_chunk_id": None,
                    "matched_page_number": None,
                    "evidence_quote": evidence_quote,
                    "metadata_json": {"engine": "checklist_v2"},
                },
                "evidence": evidence_list,
            }
        )
    return checklist_entries


def build_findings(
    rows: List[dict],
    clause_hits: List[dict],
    numeric_findings: List[dict],
    structured_clauses_by_type: Optional[Dict[str, List[dict]]] = None,
    document_classifications: Optional[Dict[str, dict]] = None,
) -> List[dict]:
    findings = []
    sc_by_type = structured_clauses_by_type or {}
    for hit in clause_hits:
        clause_type = hit["clause_type"]
        meta = CLAUSE_META[clause_type]
        ev = hit["evidence"]
        finding = {
            "category": meta["category"],
            "severity": meta["severity"],
            "title": meta["title"],
            "description": meta["description"],
            "recommendation": meta["recommendation"],
            "status": "open",
            "source_document_id": ev["source_document_id"],
            "source_chunk_id": ev["source_chunk_id"],
            "source_page_number": ev["source_page_number"],
            "evidence_quote": ev["quote"],
            "confidence": meta["confidence"],
            "metadata_json": {"engine": "clause_regex_v1", "clause_type": clause_type},
            "evidence_list": [ev],
        }
        findings.append(enrich_finding_from_structured_clause(finding, sc_by_type))

    for row in rows:
        text_norm = row["text_lower"]
        if "customer concentration" in text_norm:
            idx = text_norm.find("customer concentration")
            ev = make_evidence(
                row=row,
                start=idx,
                end=idx + len("customer concentration"),
                quote=clip_quote(row["text"], idx, idx + len("customer concentration")),
                confidence=0.82,
                metadata={"engine": "keyword_v1", "risk_type": "customer_concentration"},
            )
            findings.append(
                {
                    "category": "commercial",
                    "severity": "medium",
                    "title": "Customer concentration risk",
                    "description": "Customer concentration language indicates possible dependency on a small number of accounts.",
                    "recommendation": "Request top-customer revenue split for last 24 months.",
                    "status": "open",
                    "source_document_id": ev["source_document_id"],
                    "source_chunk_id": ev["source_chunk_id"],
                    "source_page_number": ev["source_page_number"],
                    "evidence_quote": ev["quote"],
                    "confidence": 0.82,
                    "metadata_json": {"engine": "risk_rule_v1"},
                    "evidence_list": [ev],
                }
            )
            break

    findings.extend(numeric_findings)
    if document_classifications:
        findings.extend(detect_missing_clauses(clause_hits, document_classifications, rows))
    return normalize_findings(findings, source_kind="rule_based", limit=25)


_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def sort_findings_for_triage(findings: List[dict]) -> List[dict]:
    return sorted(
        findings,
        key=lambda finding: (
            _SEVERITY_RANK.get(finding.get("severity"), 3),
            0 if finding.get("status", "open") == "open" else 1,
            -(finding.get("confidence") or 0.0),
            finding.get("title") or "",
        ),
    )


def build_top_risks(findings: List[dict], limit: int = 5) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []
    for finding in sort_findings_for_triage(findings)[:limit]:
        evidence = (finding.get("evidence_list") or [None])[0]
        risks.append(
            {
                "title": finding.get("title"),
                "severity": finding.get("severity"),
                "summary": finding.get("description"),
                "category": finding.get("category"),
                "status": finding.get("status", "open"),
                "confidence": finding.get("confidence"),
                "playbook_slug": (finding.get("metadata_json") or {}).get("playbook_slug"),
                "clause_type": (finding.get("metadata_json") or {}).get("clause_type"),
                "source_document_id": finding.get("source_document_id") or (evidence or {}).get("source_document_id"),
                "source_page_number": finding.get("source_page_number") or (evidence or {}).get("source_page_number"),
                "evidence_quote": ((evidence or {}).get("quote") or finding.get("evidence_quote") or "")[:220],
            }
        )
    return risks


def _primary_evidence_reference(item: dict) -> Dict[str, Any]:
    evidence = (item.get("evidence_list") or [None])[0]
    return {
        "source_document_id": item.get("source_document_id") or (evidence or {}).get("source_document_id"),
        "source_page_number": item.get("source_page_number") or (evidence or {}).get("source_page_number"),
        "evidence_quote": ((evidence or {}).get("quote") or item.get("evidence_quote") or "")[:220],
    }


def build_contradictions(findings: List[dict], limit: int = 5) -> List[Dict[str, Any]]:
    contradictions: List[Dict[str, Any]] = []
    for finding in sort_findings_for_triage(findings):
        title = str(finding.get("title") or "")
        metadata = finding.get("metadata_json") or {}
        is_conflict = (
            finding.get("category") == "numeric_reconciliation"
            or metadata.get("engine") == "numeric_recon_v1"
            or any(token in title.lower() for token in ["inconsistent", "mismatch", "conflict", "reconcile", "sanity check"])
        )
        if not is_conflict:
            continue
        contradictions.append(
            {
                "title": title,
                "severity": finding.get("severity"),
                "summary": finding.get("description"),
                "metric": metadata.get("metric"),
                "spread_ratio": metadata.get("spread_ratio"),
                **_primary_evidence_reference(finding),
            }
        )
        if len(contradictions) >= limit:
            break
    return contradictions


def build_coverage_summary(checklist_entries: List[dict], document_classifications: Dict[str, dict]) -> Dict[str, Any]:
    checklist_items = [entry["item"] for entry in checklist_entries]
    by_category: Dict[str, Dict[str, Any]] = {}
    for item in checklist_items:
        category = item.get("category") or "general"
        bucket = by_category.setdefault(category, {"category": category, "covered": 0, "partial": 0, "missing": 0, "required_missing": 0, "total": 0})
        bucket["total"] += 1
        status = item.get("status") or "missing"
        if status in {"covered", "partial", "missing"}:
            bucket[status] += 1
        if item.get("required") and status == "missing":
            bucket["required_missing"] += 1

    workstreams = []
    for category, bucket in by_category.items():
        total = bucket["total"] or 1
        covered_like = bucket["covered"] + bucket["partial"]
        completion_pct = round(covered_like * 100.0 / total, 2)
        status = "gap" if bucket["required_missing"] > 0 else "partial" if bucket["missing"] > 0 else "covered"
        workstreams.append({**bucket, "completion_pct": completion_pct, "status": status})

    workstreams.sort(key=lambda bucket: (0 if bucket["status"] == "gap" else 1 if bucket["status"] == "partial" else 2, -bucket["required_missing"], bucket["category"]))

    missing_required_items = [
        {"item_key": item.get("item_key"), "title": item.get("title"), "category": item.get("category"), "priority": item.get("priority")}
        for item in checklist_items if item.get("required") and item.get("status") == "missing"
    ]

    doc_type_counts = defaultdict(int)
    needs_review_docs = 0
    for row in document_classifications.values():
        doc_type_counts[row.get("document_type") or DEFAULT_DOC_TYPE] += 1
        if row.get("needs_review"):
            needs_review_docs += 1

    return {
        "workstreams": workstreams,
        "missing_required_items": missing_required_items[:8],
        "document_type_counts": dict(doc_type_counts),
        "classification_review_count": needs_review_docs,
    }


def build_suggested_investigations(checklist_entries: List[dict], top_risks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    suggestions: List[Dict[str, str]] = []
    seen: set[str] = set()

    def _add(slug: str, title: str, rationale: str) -> None:
        if slug not in seen:
            suggestions.append({"slug": slug, "title": title, "rationale": rationale})
            seen.add(slug)

    risk_text = " ".join(
        " ".join(filter(None, [str(risk.get("title") or ""), str(risk.get("summary") or ""), str(risk.get("clause_type") or ""), str(risk.get("playbook_slug") or "")])).lower()
        for risk in top_risks
    )
    checklist_by_key = {entry["item"].get("item_key"): entry["item"] for entry in checklist_entries}

    if any(token in risk_text for token in ["change_of_control", "change-of-control", "assignment", "consent"]):
        _add("change_of_control", "Change of Control Exposure", "Several findings point to consent, assignment, or ownership-transfer restrictions that could delay closing.")
    if checklist_by_key.get("customer_concentration", {}).get("status") in {"missing", "partial"} or any(token in risk_text for token in ["customer", "mfn", "exclusivity", "termination for convenience"]):
        _add("customer_concentration", "Customer Concentration & Contract Risk", "Commercial exposure looks incomplete or risky; analyst should quantify revenue at risk and contract churn exposure.")
    if checklist_by_key.get("vendor_supplier_concentration", {}).get("status") in {"missing", "partial"} or any(token in risk_text for token in ["supplier", "vendor", "sole source", "minimum commitment"]):
        _add("supplier_contracts", "Supplier Dependency", "Vendor and supply terms may create continuity or margin risk that merits a focused review.")
    if checklist_by_key.get("tax_structure", {}).get("status") in {"missing", "partial"} or "tax" in risk_text:
        _add("tax_exposure", "Tax Exposure", "Tax support is incomplete or findings suggest indemnity, NOL, or audit exposure that should be escalated.")
    if checklist_by_key.get("ip_assets", {}).get("status") in {"missing", "partial"} or any(token in risk_text for token in ["ip", "license", "royalty", "assignment"]):
        _add("ip_ownership", "IP Chain of Title", "IP ownership and license scope should be confirmed before relying on the asset base in the thesis.")
    return suggestions[:4]


def build_management_questions(top_risks: List[Dict[str, Any]], coverage: Dict[str, Any]) -> List[Dict[str, str]]:
    questions: List[Dict[str, str]] = []
    for risk in top_risks[:3]:
        title = risk.get("title") or "this issue"
        category = (risk.get("category") or "general").replace("_", " ")
        questions.append({
            "question": f"What is management's mitigation plan for {title.lower()}?",
            "rationale": f"Current analysis surfaced this as a {risk.get('severity', 'medium')} severity {category} issue.",
            "related_finding": risk.get("clause_type") or risk.get("playbook_slug") or title,
        })
    for item in coverage.get("missing_required_items", [])[:2]:
        questions.append({
            "question": f"Can management provide support for {item.get('title')}?",
            "rationale": "This is a required diligence item and the current room does not contain enough evidence to mark it covered.",
            "related_finding": item.get("item_key"),
        })
    return questions[:5]


def build_follow_up_requests(coverage: Dict[str, Any]) -> List[Dict[str, str]]:
    requests = [
        {
            "title": item.get("title") or "Missing diligence support",
            "priority": "high" if (item.get("priority") or 3) <= 1 else "medium",
            "reason": "Required diligence item is still not covered by the room contents.",
            "request": f"Request materials supporting {item.get('title')}.",
        }
        for item in coverage.get("missing_required_items", [])[:5]
    ]
    if coverage.get("classification_review_count", 0) > 0:
        requests.append({
            "title": "Document classification review",
            "priority": "medium",
            "reason": "Some documents were classified generically or ambiguously and may be under-routed in baseline analysis.",
            "request": "Review low-confidence document classifications before relying on workstream coverage.",
        })
    return requests[:6]


def build_document_gap_register(
    coverage: Dict[str, Any],
    missing_key_documents: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    register: List[Dict[str, Any]] = []
    for item in coverage.get("missing_required_items", [])[:6]:
        register.append(
            {
                "gap_type": "required_item",
                "title": item.get("title") or "Missing required diligence support",
                "category": item.get("category"),
                "priority": "high" if (item.get("priority") or 3) <= 1 else "medium",
                "detail": "Required checklist item is not yet covered by room evidence.",
            }
        )

    for item in missing_key_documents[:6]:
        register.append(
            {
                "gap_type": "missing_document_family",
                "title": item.get("title") or "Missing document family",
                "priority": "medium",
                "detail": item.get("reason"),
                "expected_doc_types": item.get("expected_doc_types") or [],
            }
        )

    if coverage.get("classification_review_count", 0) > 0:
        register.append(
            {
                "gap_type": "classification_review",
                "title": "Document classification review queue",
                "priority": "medium",
                "detail": f"{coverage.get('classification_review_count', 0)} documents still need classification review before relying on workstream coverage.",
            }
        )
    return register[:10]


def build_deal_blockers(
    top_risks: List[Dict[str, Any]],
    coverage: Dict[str, Any],
    verification_stats: Dict[str, int],
) -> List[Dict[str, Any]]:
    blockers: List[Dict[str, Any]] = []
    for risk in top_risks:
        if risk.get("severity") != "high" or risk.get("status", "open") != "open":
            continue
        blockers.append(
            {
                "blocker_type": "risk",
                "title": risk.get("title"),
                "severity": risk.get("severity"),
                "detail": risk.get("summary"),
                "category": risk.get("category"),
                "source_document_id": risk.get("source_document_id"),
                "source_page_number": risk.get("source_page_number"),
                "evidence_quote": risk.get("evidence_quote"),
            }
        )

    for item in coverage.get("missing_required_items", [])[:4]:
        blockers.append(
            {
                "blocker_type": "diligence_gap",
                "title": item.get("title"),
                "severity": "high" if (item.get("priority") or 3) <= 1 else "medium",
                "detail": "Required diligence item remains uncovered in the room.",
                "category": item.get("category"),
            }
        )

    if verification_stats.get("needs_review", 0) >= 3:
        blockers.append(
            {
                "blocker_type": "verification_queue",
                "title": "Multiple findings still need review",
                "severity": "medium",
                "detail": f"{verification_stats.get('needs_review', 0)} findings still require analyst verification.",
            }
        )

    return blockers[:8]


def build_valuation_signals(findings: List[dict], llm_financials: Optional[dict]) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []

    historical = (llm_financials or {}).get("historical") or []
    latest_period = historical[-1] if historical else None
    currency = (llm_financials or {}).get("currency") or "USD"
    if latest_period:
        metrics = []
        for key in ("revenue", "ebitda", "ebitda_margin", "free_cash_flow"):
            value = latest_period.get(key)
            if value is not None:
                metrics.append({"metric": key, "value": value, "currency": currency if key != "ebitda_margin" else None})
        if metrics:
            signals.append(
                {
                    "signal_type": "financial_snapshot",
                    "title": f"Latest financial snapshot ({latest_period.get('year', 'latest period')})",
                    "detail": "Latest extracted baseline metrics available for underwriting.",
                    "metrics": metrics,
                }
            )

    for finding in sort_findings_for_triage(findings):
        if finding.get("status", "open") != "open":
            continue
        if finding.get("category") not in {"financial", "commercial", "debt", "spa", "numeric_reconciliation"}:
            continue
        signals.append(
            {
                "signal_type": "risk",
                "title": finding.get("title"),
                "severity": finding.get("severity"),
                "category": finding.get("category"),
                "detail": finding.get("description"),
                **_primary_evidence_reference(finding),
            }
        )
        if len(signals) >= 6:
            break

    data_quality_notes = (llm_financials or {}).get("data_quality_notes")
    if data_quality_notes:
        signals.append(
            {
                "signal_type": "data_quality",
                "title": "Financial data quality note",
                "severity": "medium",
                "detail": data_quality_notes,
            }
        )
    return signals[:7]


def build_data_quality_assessment(llm_financials: Optional[dict], contradictions: List[Dict[str, Any]]) -> Optional[str]:
    notes = (llm_financials or {}).get("data_quality_notes")
    if notes:
        return str(notes)
    if contradictions:
        return "Cross-document numeric inconsistencies were detected. Reconcile definitions and periods before relying on base-case underwriting."
    return None


def build_ic_readiness(
    deal_blockers: List[Dict[str, Any]],
    coverage: Dict[str, Any],
    verification_stats: Dict[str, int],
    document_gap_register: List[Dict[str, Any]],
) -> Dict[str, Any]:
    blocker_count = len(deal_blockers)
    required_gap_count = len(coverage.get("missing_required_items") or [])
    verification_review_count = verification_stats.get("needs_review", 0)
    classification_review_count = coverage.get("classification_review_count", 0)

    if blocker_count > 0 or required_gap_count > 0:
        status = "not_ready"
        headline = "Not ready for IC draft"
        next_step = "Clear high-severity blockers and fill required diligence gaps before drafting IC materials."
    elif verification_review_count > 0 or classification_review_count > 0 or document_gap_register:
        status = "caution"
        headline = "Usable for working draft with caution"
        next_step = "Use for internal underwriting only until review queues and document gaps are resolved."
    else:
        status = "ready_for_draft"
        headline = "Ready for IC draft support"
        next_step = "Proceed to IC memo drafting and targeted confirmatory investigations."

    return {
        "status": status,
        "headline": headline,
        "blocker_count": blocker_count,
        "required_gap_count": required_gap_count,
        "verification_review_count": verification_review_count,
        "classification_review_count": classification_review_count,
        "recommended_next_step": next_step,
    }


def _doc_type_label(doc_type: str) -> str:
    return (DOC_TYPE_METADATA.get(doc_type) or {}).get("label") or doc_type.replace("_", " ").title()


def build_missing_key_documents(checklist_entries: List[dict], document_classifications: Dict[str, dict]) -> List[Dict[str, Any]]:
    doc_type_counts = defaultdict(int)
    for row in document_classifications.values():
        doc_type_counts[row.get("document_type") or DEFAULT_DOC_TYPE] += 1

    expected_families = [
        {"slug": "transaction_docs", "title": "Core transaction documents", "doc_types": [PEDocumentType.PURCHASE_AGREEMENT.value, PEDocumentType.MERGER_AGREEMENT.value, PEDocumentType.DISCLOSURE_SCHEDULE.value], "reason": "Baseline analysis needs signed transaction documents and schedules to assess core deal mechanics."},
        {"slug": "financial_docs", "title": "Historical financial package", "doc_types": [PEDocumentType.FINANCIAL_STATEMENT.value, PEDocumentType.QOE_REPORT.value], "reason": "Analysts need financial statements or QoE support to test earnings quality and model assumptions."},
        {"slug": "commercial_docs", "title": "Key commercial contracts", "doc_types": [PEDocumentType.CUSTOMER_CONTRACT.value, PEDocumentType.VENDOR_CONTRACT.value], "reason": "Commercial diligence is weak without customer and supplier contracts tied to concentration and change-of-control risk."},
        {"slug": "tax_and_regulatory", "title": "Tax and regulatory support", "doc_types": [PEDocumentType.TAX_DOCUMENT.value, PEDocumentType.REGULATORY_FILING.value, PEDocumentType.POLICY_DOCUMENT.value], "reason": "Tax, compliance, and regulatory workstreams need explicit source documents, not just generic contract references."},
        {"slug": "governance_docs", "title": "Governance and equity documents", "doc_types": [PEDocumentType.SHAREHOLDER_AGREEMENT.value, PEDocumentType.CHARTER_DOCUMENT.value, PEDocumentType.EMPLOYMENT_AGREEMENT.value], "reason": "Governance control, rollover, and management incentive analysis depend on shareholder, charter, and employment materials."},
        {"slug": "insurance_docs", "title": "Insurance package", "doc_types": [PEDocumentType.INSURANCE_DOCUMENT.value], "reason": "Insurance diligence remains incomplete without actual policy and tail coverage materials."},
    ]

    checklist_by_key = {entry["item"].get("item_key"): entry["item"] for entry in checklist_entries}
    checklist_gap_map = {
        "transaction_docs": checklist_by_key.get("spa_transaction_terms", {}).get("status") == "missing",
        "financial_docs": checklist_by_key.get("financial_statements", {}).get("status") == "missing",
        "commercial_docs": any(checklist_by_key.get(key, {}).get("status") in {"missing", "partial"} for key in ("customer_concentration", "vendor_supplier_concentration")),
        "tax_and_regulatory": any(checklist_by_key.get(key, {}).get("status") in {"missing", "partial"} for key in ("tax_structure", "regulatory_compliance", "data_privacy")),
        "governance_docs": any(checklist_by_key.get(key, {}).get("status") in {"missing", "partial"} for key in ("related_party_transactions", "management_incentive_plan", "hr_roster")),
        "insurance_docs": checklist_by_key.get("insurance_coverage", {}).get("status") in {"missing", "partial"},
    }

    missing = []
    for family in expected_families:
        present_count = sum(doc_type_counts.get(doc_type, 0) for doc_type in family["doc_types"])
        if present_count > 0 and not checklist_gap_map.get(family["slug"]):
            continue
        missing.append({
            "slug": family["slug"],
            "title": family["title"],
            "reason": family["reason"],
            "expected_doc_types": [{"type": doc_type, "label": _doc_type_label(doc_type)} for doc_type in family["doc_types"]],
        })
    return missing[:6]


def build_ic_memo_inputs(top_risks: List[Dict[str, Any]], coverage: Dict[str, Any], suggested_investigations: List[Dict[str, str]], llm_financials: Optional[dict]) -> Dict[str, Any]:
    historical = (llm_financials or {}).get("historical") or []
    latest_period = historical[-1] if historical else {}
    financial_snapshot = {}
    for field in ("year", "revenue", "ebitda", "ebitda_margin", "net_income", "free_cash_flow", "currency"):
        value = latest_period.get(field) if field != "currency" else (llm_financials or {}).get("currency")
        if value is not None:
            financial_snapshot[field] = value
    return {
        "status": "draft_inputs_only",
        "note": "These are baseline analysis inputs for memo and model drafting, not a final IC memo.",
        "top_issues_for_memo": [{"title": risk.get("title"), "severity": risk.get("severity"), "summary": risk.get("summary")} for risk in top_risks[:5]],
        "critical_gaps": [item.get("title") for item in coverage.get("missing_required_items", [])[:5]],
        "recommended_investigations": [item.get("title") for item in suggested_investigations[:4]],
        "financial_snapshot": financial_snapshot,
    }


def build_triage_summary(top_risks: List[Dict[str, Any]], coverage: Dict[str, Any], verification_stats: Dict[str, int]) -> Dict[str, Any]:
    high_count = sum(1 for risk in top_risks if risk.get("severity") == "high")
    required_gaps = len(coverage.get("missing_required_items") or [])
    needs_review = coverage.get("classification_review_count", 0)
    if high_count or required_gaps:
        headline = f"{high_count} high-severity risk{'s' if high_count != 1 else ''} and {required_gaps} required diligence gap{'s' if required_gaps != 1 else ''} need attention."
    else:
        headline = "No immediate deal-breakers surfaced, but the room still needs normal confirmatory review."
    next_actions = [risk.get("title") for risk in top_risks[:3] if risk.get("title")]
    next_actions.extend(f"Fill missing required support for {item.get('title')}" for item in coverage.get("missing_required_items", [])[:2] if item.get("title"))
    return {
        "headline": headline,
        "high_risk_count": high_count,
        "required_gap_count": required_gaps,
        "classification_review_count": needs_review,
        "verification_review_count": verification_stats.get("needs_review", 0),
        "next_actions": next_actions[:5],
    }


def build_summary(room_name: str, checklist_entries: List[dict], finding_entries: List[dict], document_classifications: Dict[str, dict], verification_stats: Dict[str, int], llm_financials: Optional[dict] = None) -> Dict[str, Any]:
    checklist_items = [entry.get("item") or {} for entry in checklist_entries if isinstance(entry, dict)]
    findings = finding_entries
    covered = sum(1 for item in checklist_items if item.get("status") in {"covered", "partial"})
    total = len(checklist_items)
    completion = 0.0 if total == 0 else round(covered * 100.0 / total, 2)
    high = sum(1 for finding in findings if finding.get("severity") == "high")
    medium = sum(1 for finding in findings if finding.get("severity") == "medium")
    low = sum(1 for finding in findings if finding.get("severity") == "low")

    doc_type_counts = defaultdict(int)
    for row in document_classifications.values():
        doc_type_counts[row.get("document_type") or DEFAULT_DOC_TYPE] += 1

    coverage = build_coverage_summary(checklist_entries, document_classifications)
    top_risks = build_top_risks(findings)
    suggested_investigations = build_suggested_investigations(checklist_entries, top_risks)
    triage = build_triage_summary(top_risks, coverage, verification_stats)
    management_questions = build_management_questions(top_risks, coverage)
    follow_up_requests = build_follow_up_requests(coverage)
    missing_key_documents = build_missing_key_documents(checklist_entries, document_classifications)
    contradictions = build_contradictions(findings)
    valuation_signals = build_valuation_signals(findings, llm_financials)
    document_gap_register = build_document_gap_register(coverage, missing_key_documents)
    deal_blockers = build_deal_blockers(top_risks, coverage, verification_stats)
    ic_readiness = build_ic_readiness(deal_blockers, coverage, verification_stats, document_gap_register)
    ic_memo_inputs = build_ic_memo_inputs(top_risks, coverage, suggested_investigations, llm_financials)
    data_quality_assessment = build_data_quality_assessment(llm_financials, contradictions)

    markdown = "\n".join([
        f"# Diligence Overview - {room_name}",
        "",
        f"- Checklist coverage: **{covered}/{total}** ({completion}%)",
        f"- Findings: **{len(findings)}** (High: {high}, Medium: {medium}, Low: {low})",
        f"- Verification: **{verification_stats.get('verified', 0)} verified**, **{verification_stats.get('needs_review', 0)} needs review**",
        f"- Document types detected: {dict(doc_type_counts)}",
        "",
        "## Triage",
        triage["headline"],
        *(f"- {action}" for action in triage["next_actions"]),
        "",
        "## Top Risks",
        *([f"{idx}. **[{(risk.get('severity') or 'medium').capitalize()}] {risk.get('title', '')}** — {risk.get('summary', '')}" for idx, risk in enumerate(top_risks[:5], 1)] or ["1. No material risks surfaced in the current baseline analysis."]),
        "",
        "## Coverage Gaps",
        *([f"- {item.get('title')} ({item.get('category')})" for item in coverage.get("missing_required_items", [])[:5]] or ["- No required gaps detected."]),
        "",
        "## IC Readiness",
        f"- Status: **{ic_readiness['headline']}**",
        f"- Recommended next step: {ic_readiness['recommended_next_step']}",
        "",
        "## Missing Materials / Follow-Up Requests",
        *([f"- {item['request']}" for item in follow_up_requests] or ["- No immediate follow-up requests generated."]),
        "",
        "## Suggested Management Questions",
        *([f"{idx}. {question['question']}" for idx, question in enumerate(management_questions, 1)] or ["1. Confirm whether any material diligence items remain outside the room."]),
    ])

    citations = []
    for finding in findings[:5]:
        ev = (finding.get("evidence_list") or [None])[0]
        citations.append({
            "entity": finding.get("title") or "Supporting evidence",
            "document_id": ev.get("source_document_id") if ev else None,
            "page_number": ev.get("source_page_number") if ev else None,
            "quote": (ev.get("quote") if ev else (finding.get("evidence_quote") or ""))[:220],
            "confidence": ev.get("confidence") if ev else finding.get("confidence"),
        })

    summary_evidence = [finding["evidence_list"][0] for finding in findings if finding.get("evidence_list") and isinstance(finding["evidence_list"][0], dict)][:5]
    return normalize_summary_payload({
        "markdown": markdown,
        "citations": citations,
        "confidence": 0.78,
        "evidence_list": summary_evidence,
        "metadata": {
            "overview": {
                "completion_pct": completion,
                "covered_count": covered,
                "total_checklist_items": total,
                "findings_count": len(findings),
                "high_findings_count": high,
                "medium_findings_count": medium,
                "low_findings_count": low,
                "verified_count": verification_stats.get("verified", 0),
                "needs_review_count": verification_stats.get("needs_review", 0),
                "document_type_counts": dict(doc_type_counts),
            },
            "triage": triage,
            "coverage": coverage,
            "top_risks": top_risks,
            "contradictions": contradictions,
            "valuation_signals": valuation_signals,
            "deal_blockers": deal_blockers,
            "management_questions": management_questions,
            "follow_up_requests": follow_up_requests,
            "missing_key_documents": missing_key_documents,
            "document_gap_register": document_gap_register,
            "ic_memo_inputs": ic_memo_inputs,
            "ic_readiness": ic_readiness,
            "suggested_investigations": suggested_investigations,
            "data_quality_assessment": data_quality_assessment,
            "document_classification": document_classifications,
            "verification": verification_stats,
        },
    })


def build_document_classification_summary(document_classifications: Dict[str, dict]) -> Dict[str, Any]:
    doc_type_counts: Dict[str, int] = defaultdict(int)
    needs_review = 0
    for row in document_classifications.values():
        doc_type = row.get("document_type") or DEFAULT_DOC_TYPE
        doc_type_counts[doc_type] += 1
        if row.get("needs_review"):
            needs_review += 1
    return {"total": len(document_classifications), "needs_review": needs_review, "document_type_counts": dict(doc_type_counts)}
