from app.verticals.private_equity.diligence.normalization import (
    normalize_evidence_records,
    normalize_findings,
    normalize_llm_financials,
    normalize_summary_payload,
)
from app.verticals.private_equity.diligence.reporting import build_summary
from app.verticals.private_equity.diligence.verifier import verify_findings


def test_normalize_llm_financials_filters_invalid_rows_and_clamps_confidence():
    raw = {
        "currency": "usd",
        "historical": [
            {"year": "2024", "revenue": "125.4", "ebitda": 20},
            {"year": "2023"},
            "bad-row",
        ],
        "ratios": [
            {"metric_name": "leverage_ratio", "value": "3.4", "confidence": 1.8, "raw_quote": "Net leverage 3.4x"},
            {"metric_name": "", "value": 2.0},
        ],
        "other_metrics": None,
        "data_quality_notes": "  Missing quarterly bridge  ",
    }

    normalized = normalize_llm_financials(raw)

    assert normalized is not None
    assert normalized["currency"] == "USD"
    assert normalized["historical"] == [
        {
            "year": "2024",
            "revenue": 125.4,
            "ebitda": 20.0,
            "ebitda_margin": None,
            "gross_profit": None,
            "net_income": None,
            "capex": None,
            "free_cash_flow": None,
        }
    ]
    assert normalized["ratios"] == [
        {
            "metric_name": "leverage_ratio",
            "value": 3.4,
            "unit": None,
            "period": None,
            "definition": None,
            "raw_quote": "Net leverage 3.4x",
            "confidence": 1.0,
        }
    ]
    assert normalized["data_quality_notes"] == "Missing quarterly bridge"


def test_normalize_summary_payload_uses_fallback_and_filters_invalid_evidence():
    fallback = {
        "markdown": "# Fallback",
        "citations": [{"entity": "Fallback", "quote": "Fallback quote", "confidence": 0.5}],
        "confidence": 0.7,
        "evidence_list": [{"quote": "Fallback evidence", "source_document_id": "doc-1"}],
        "metadata": {
            "top_risks": [
                {
                    "title": "Cap exposure",
                    "summary": "Cap may be too low",
                    "severity": "high",
                    "status": "open",
                    "source_document_id": "doc-1",
                }
            ]
        },
    }
    payload = {
        "markdown": "",
        "citations": [None, {"entity": "", "quote": ""}],
        "confidence": "bad",
        "evidence_list": [{"quote": "   "}, {"quote": "Valid evidence", "source_document_id": "doc-2"}],
        "metadata": {"management_questions": [{"question": "What changed?", "rationale": 123}]},
    }

    normalized = normalize_summary_payload(payload, fallback=fallback)

    assert normalized["markdown"] == "# Fallback"
    assert normalized["confidence"] == 0.0
    assert normalized["citations"] == []
    assert normalized["evidence_list"] == [
        {
            "source_document_id": "doc-2",
            "source_chunk_id": None,
            "source_page_number": None,
            "char_start": None,
            "char_end": None,
            "quote": "Valid evidence",
            "confidence": 0.0,
            "metadata_json": None,
        }
    ]
    assert normalized["metadata"]["top_risks"][0]["source_document_id"] == "doc-1"
    assert normalized["metadata"]["management_questions"][0]["rationale"] == "123"


def test_build_summary_handles_partial_findings_without_key_errors():
    checklist_entries = [
        {
            "item": {
                "item_key": "financial_statements",
                "title": "Financial Statements",
                "category": "financials",
                "priority": 1,
                "required": True,
                "status": "missing",
            },
            "evidence": [],
        }
    ]
    finding_entries = [
        {
            "title": "Revenue mismatch",
            "description": "Different revenue values appear across documents.",
            "category": "numeric_reconciliation",
            "status": "open",
            "metadata_json": {"engine": "numeric_recon_v1", "metric": "revenue", "spread_ratio": 1.4},
            "evidence_list": [{"quote": "Revenue was 100 in one source and 140 in another.", "source_document_id": "doc-1", "source_page_number": 3}],
        }
    ]

    summary = build_summary(
        "Test Room",
        checklist_entries,
        finding_entries,
        document_classifications={"doc-1": {"document_type": "financial_statement", "needs_review": True}},
        verification_stats={"verified": 0, "needs_review": 1, "total": 1},
        llm_financials=None,
    )

    assert summary["markdown"].startswith("# Diligence Overview - Test Room")
    assert summary["metadata"]["contradictions"][0]["metric"] == "revenue"
    assert summary["metadata"]["ic_readiness"]["status"] == "not_ready"
    assert summary["citations"][0]["entity"] == "Revenue mismatch"


def test_normalize_evidence_records_filters_entries_without_quotes():
    normalized = normalize_evidence_records([
        {"quote": "", "source_document_id": "doc-1"},
        {"quote": "Important excerpt", "source_document_id": "doc-2", "confidence": "0.91"},
        "bad-row",
    ])

    assert normalized == [
        {
            "source_document_id": "doc-2",
            "source_chunk_id": None,
            "source_page_number": None,
            "char_start": None,
            "char_end": None,
            "quote": "Important excerpt",
            "confidence": 0.91,
            "metadata_json": None,
        }
    ]


def test_normalize_findings_adds_workflow_metadata_and_fallback_evidence():
    normalized = normalize_findings([
        {
            "category": "tax",
            "severity": "high",
            "title": "Tax covenant carveout broadens exposure",
            "description": "Tax indemnity carveout appears broader than expected for the deal structure.",
            "recommendation": "",
            "status": "open",
            "source_document_id": "doc-7",
            "source_page_number": "12",
            "evidence_quote": "Seller remains liable for pre-closing taxes except as otherwise limited.",
            "confidence": "0.84",
            "metadata_json": {"engine": "per_doc_llm_v2", "assessment": "flagged", "supporting_evidence": ["tax_indemnity", "tax_indemnity"]},
            "evidence_list": [],
        }
    ])

    assert len(normalized) == 1
    finding = normalized[0]
    assert finding["recommendation"]
    assert finding["source_page_number"] == 12
    assert finding["evidence_list"][0]["quote"].startswith("Seller remains liable")
    assert finding["metadata_json"]["workflow"]["bucket"] == "ic_blocker"
    assert finding["metadata_json"]["workflow"]["owner_hint"] == "specialist"
    assert finding["metadata_json"]["supporting_evidence"] == ["tax_indemnity"]


def test_verify_findings_marks_specialist_and_underwriting_reviews():
    findings = normalize_findings([
        {
            "category": "tax",
            "severity": "high",
            "title": "Tax exposure flagged",
            "description": "Potential pre-close tax leakage remains unresolved.",
            "source_document_id": "doc-1",
            "source_page_number": 7,
            "evidence_quote": "Seller remains liable for pre-closing taxes.",
            "confidence": 0.84,
            "metadata_json": {"assessment": "flagged", "engine": "per_doc_llm_v2"},
        },
        {
            "category": "financial",
            "severity": "medium",
            "title": "Revenue quality needs reconciliation",
            "description": "Reported revenue bridge is incomplete across periods.",
            "source_document_id": "doc-2",
            "source_page_number": 14,
            "evidence_quote": "Revenue excludes certain pass-through items.",
            "confidence": 0.79,
            "metadata_json": {"engine": "llm_synthesis_v2"},
        },
    ])

    verified, stats = verify_findings(findings)

    assert stats["needs_review"] == 2
    assert stats["specialist_review"] == 1
    assert stats["underwriting_only"] == 1
    assert stats["high_priority_review"] == 1
    assert "specialist_review_required" in verified[0]["metadata_json"]["verification"]["reasons"]
    assert "underwriting_needs_confirmation" in verified[1]["metadata_json"]["verification"]["reasons"]
    assert verified[0]["metadata_json"]["verification"]["review_priority"] == "high"
