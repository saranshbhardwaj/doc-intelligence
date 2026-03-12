"""Celery tasks for PE diligence analysis."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import asyncio
import re
from statistics import median
from typing import Any, Dict, List, Optional

from celery import shared_task

from app.config import settings
from app.database import SessionLocal
from app.db_models_chat import DocumentChunk
from app.utils.logging import logger
from app.verticals.private_equity.diligence.repository import PEDiligenceRepository
from app.verticals.private_equity.diligence.document_classifier import (
    apply_llm_fallback,
    build_low_confidence_inputs,
    classify_documents,
)
from app.verticals.private_equity.diligence.llm_adapter import PEDiligenceClassificationAdapter
from app.verticals.private_equity.diligence.verifier import verify_findings


CHECKLIST_TEMPLATE = [
    # Priority 1 — required
    {"item_key": "financial_statements", "title": "Financial Statements", "category": "financials", "priority": 1, "required": True},
    {"item_key": "customer_concentration", "title": "Customer Concentration", "category": "commercial", "priority": 1, "required": True},
    {"item_key": "debt_covenants", "title": "Debt & Covenant Package", "category": "legal_financial", "priority": 1, "required": True},
    {"item_key": "key_contracts", "title": "Key Contracts", "category": "legal", "priority": 2, "required": True},
    {"item_key": "regulatory_compliance", "title": "Regulatory Compliance", "category": "legal", "priority": 2, "required": True},
    {"item_key": "litigation_history", "title": "Litigation History", "category": "legal", "priority": 2, "required": True},
    # Priority 3 — optional
    {"item_key": "ip_assets", "title": "IP & Technology Assets", "category": "ip", "priority": 3, "required": False},
    {"item_key": "hr_roster", "title": "Leadership & HR Overview", "category": "people", "priority": 3, "required": False},
    {"item_key": "insurance_coverage", "title": "Insurance Coverage", "category": "legal", "priority": 3, "required": False},
    {"item_key": "tax_structure", "title": "Tax Structure", "category": "financials", "priority": 2, "required": False},
    {"item_key": "environmental", "title": "Environmental & Compliance", "category": "regulatory", "priority": 3, "required": False},
    {"item_key": "data_privacy", "title": "Data Privacy & Security", "category": "regulatory", "priority": 3, "required": False},
]

# Rules-driven checklist matching: each item_key maps to matching sources
# Keys: clause_types (list), numeric_metrics (list), doc_types (list), keywords (list),
#       check_llm_financials (bool), base_confidence, partial_status
CHECKLIST_RULES: Dict[str, dict] = {
    "financial_statements": {
        "clause_types": [],
        "numeric_metrics": ["revenue", "ebitda", "debt"],
        "doc_types": ["financial_statement", "qoe_report"],
        "keywords": [],
        "check_llm_financials": True,
        "base_confidence": 0.84,
        "partial_keywords": [],
    },
    "customer_concentration": {
        "clause_types": ["customer_contract", "revenue_share", "exclusivity", "mfn_pricing"],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["customer concentration", "top customer", "top 10 customer", "key account", "concentration risk"],
        "check_llm_financials": False,
        "base_confidence": 0.80,
        "partial_keywords": ["customer", "client"],
    },
    "debt_covenants": {
        "clause_types": ["debt_covenant", "leverage_ratio", "interest_coverage", "event_of_default", "prepayment"],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": [],
        "check_llm_financials": False,
        "base_confidence": 0.82,
        "partial_keywords": [],
    },
    "key_contracts": {
        "clause_types": ["change_of_control", "assignment_consent", "termination_penalty", "termination",
                         "customer_contract", "exclusivity", "representations_warranties"],
        "numeric_metrics": [],
        "doc_types": ["purchase_agreement", "legal_contract"],
        "keywords": [],
        "check_llm_financials": False,
        "base_confidence": 0.81,
        "partial_keywords": [],
    },
    "regulatory_compliance": {
        "clause_types": [],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["regulatory", "compliance", "regulated", "regulation", "permit", "licence", "license", "FDA", "SEC", "FINRA", "FCA"],
        "check_llm_financials": False,
        "base_confidence": 0.72,
        "partial_keywords": ["compliance"],
    },
    "litigation_history": {
        "clause_types": [],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["litigation", "lawsuit", "legal proceedings", "arbitration", "dispute", "claim", "alleged", "indictment"],
        "check_llm_financials": False,
        "base_confidence": 0.75,
        "partial_keywords": ["dispute", "claim"],
    },
    "ip_assets": {
        "clause_types": ["ip_assignment", "license_terms"],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["patent", "trademark", "intellectual property", "proprietary technology", "trade secret", "copyright"],
        "check_llm_financials": False,
        "base_confidence": 0.72,
        "partial_keywords": ["intellectual", "patent", "trademark"],
    },
    "hr_roster": {
        "clause_types": ["employment_term", "severance", "equity_vesting"],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["management team", "employee", "headcount", "key person", "key employee", "organization chart"],
        "check_llm_financials": False,
        "base_confidence": 0.70,
        "partial_keywords": ["employee", "management"],
    },
    "insurance_coverage": {
        "clause_types": [],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["insurance", "D&O", "directors and officers", "E&O", "liability coverage", "indemnification insurance", "general liability"],
        "check_llm_financials": False,
        "base_confidence": 0.70,
        "partial_keywords": ["insurance"],
    },
    "tax_structure": {
        "clause_types": [],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["tax structure", "transfer pricing", "net operating loss", "NOL", "tax jurisdiction", "tax liability", "deferred tax"],
        "check_llm_financials": False,
        "base_confidence": 0.70,
        "partial_keywords": ["tax"],
    },
    "environmental": {
        "clause_types": [],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["environmental", "ESG", "emissions", "hazardous", "remediation", "climate", "carbon", "sustainability"],
        "check_llm_financials": False,
        "base_confidence": 0.68,
        "partial_keywords": ["environmental", "ESG"],
    },
    "data_privacy": {
        "clause_types": [],
        "numeric_metrics": [],
        "doc_types": [],
        "keywords": ["GDPR", "CCPA", "data privacy", "data protection", "cybersecurity", "SOC 2", "ISO 27001", "personal data"],
        "check_llm_financials": False,
        "base_confidence": 0.68,
        "partial_keywords": ["data privacy", "cybersecurity"],
    },
}

# Missing clause expectations by document type (for _detect_missing_clauses)
EXPECTED_CLAUSES_BY_DOC_TYPE: Dict[str, List[tuple]] = {
    "purchase_agreement": [
        ("representations_warranties", "Representations & Warranties", "high"),
        ("indemnification_cap", "Indemnification / Liability Cap", "high"),
        ("material_adverse_change", "Material Adverse Change (MAC) Clause", "high"),
        ("closing_conditions", "Conditions to Closing", "medium"),
        ("purchase_price_adjustment", "Purchase Price Adjustment Mechanism", "medium"),
    ],
    "legal_contract": [
        ("change_of_control", "Change of Control Provision", "medium"),
        ("termination", "Termination Rights", "medium"),
        ("assignment_consent", "Assignment Restrictions", "low"),
    ],
}

CLAUSE_PATTERNS = {
    # ── Change of control group ──────────────────────────────────────────────
    "change_of_control": re.compile(r"\bchange[\s-]*of[\s-]*control\b", re.IGNORECASE),
    "assignment_consent": re.compile(r"\b(assign(?:ment)?|consent)\b.{0,90}\b(change[\s-]*of[\s-]*control|transfer)\b", re.IGNORECASE),
    "novation": re.compile(r"\bnovation\b", re.IGNORECASE),
    "drag_along": re.compile(r"\bdrag[\s-]*along\b", re.IGNORECASE),
    "tag_along": re.compile(r"\btag[\s-]*along\b", re.IGNORECASE),
    # ── Customer / revenue group ─────────────────────────────────────────────
    "customer_contract": re.compile(
        r"\b(master[\s-]*service[\s-]*agreement|MSA|customer[\s-]*agreement|supply[\s-]*agreement|service[\s-]*contract)\b",
        re.IGNORECASE,
    ),
    "revenue_share": re.compile(r"\brevenue[\s-]*shar(e|ing)\b", re.IGNORECASE),
    "exclusivity": re.compile(r"\b(exclusiv(e|ity)|sole[\s-]*source|exclusive[\s-]*supplier)\b", re.IGNORECASE),
    "mfn_pricing": re.compile(r"\b(most[\s-]*favou?red[\s-]*nation|MFN\b|best[\s-]*price[\s-]*guarantee)\b", re.IGNORECASE),
    "termination": re.compile(
        r"\btermination\b.{0,80}\b(for[\s-]*convenience|without[\s-]*cause|at[\s-]*will|upon[\s-]*notice)\b",
        re.IGNORECASE,
    ),
    # existing (keep for backward compat)
    "termination_penalty": re.compile(r"\btermination\b.{0,90}\b(penalt(y|ies)|fee|liquidated damages)\b", re.IGNORECASE),
    # ── Debt / covenant group ────────────────────────────────────────────────
    "debt_covenant": re.compile(r"\b(covenant|leverage ratio|debt service|interest coverage)\b", re.IGNORECASE),
    "leverage_ratio": re.compile(
        r"\b(leverage[\s-]*ratio|total[\s-]*net[\s-]*leverage|senior[\s-]*secured[\s-]*leverage|net[\s-]*leverage)\b",
        re.IGNORECASE,
    ),
    "interest_coverage": re.compile(r"\b(interest[\s-]*coverage|fixed[\s-]*charge[\s-]*coverage|FCCR\b|DSCR\b)\b", re.IGNORECASE),
    "event_of_default": re.compile(r"\b(event[\s-]*of[\s-]*default|cross[\s-]*default|payment[\s-]*default)\b", re.IGNORECASE),
    "prepayment": re.compile(
        r"\b(prepayment|prepay\b|make[\s-]*whole|call[\s-]*premium|early[\s-]*redemption|voluntary[\s-]*prepayment)\b",
        re.IGNORECASE,
    ),
    # ── IP group ─────────────────────────────────────────────────────────────
    "ip_assignment": re.compile(
        r"\b(ip[\s-]*assignment|intellectual[\s-]*property[\s-]*assign|work[\s-]*for[\s-]*hire|work[\s-]*made[\s-]*for[\s-]*hire)\b",
        re.IGNORECASE,
    ),
    "license_terms": re.compile(r"\b(licens(e|or|ee|ing)|royalt(y|ies)|sublicens)\b", re.IGNORECASE),
    "non_compete": re.compile(r"\bnon[\s-]*compet(e|ition|itive)\b", re.IGNORECASE),
    "non_solicit": re.compile(r"\bnon[\s-]*solicit(ation)?\b", re.IGNORECASE),
    # ── Employment group ─────────────────────────────────────────────────────
    "employment_term": re.compile(
        r"\b(employment[\s-]*agreement|employment[\s-]*contract|term[\s-]*of[\s-]*employment|at[\s-]*will[\s-]*employment)\b",
        re.IGNORECASE,
    ),
    "severance": re.compile(r"\b(severance[\s-]*(pay|package|agreement)?|separation[\s-]*agreement|termination[\s-]*benefits)\b", re.IGNORECASE),
    "equity_vesting": re.compile(
        r"\b(vest(ing|ed)\b|stock[\s-]*option|restricted[\s-]*stock|RSU\b|profits?[\s-]*interest|LTIP\b)\b",
        re.IGNORECASE,
    ),
    # ── SPA core group ───────────────────────────────────────────────────────
    "representations_warranties": re.compile(
        r"\b(representations?[\s,]+warranties|reps?[\s,]+and[\s,]+warranties|R&W\b|representations?\s+set\s+forth)\b",
        re.IGNORECASE,
    ),
    "indemnification_cap": re.compile(r"\bindemnif(y|ication|ied|ier)\b", re.IGNORECASE),
    "material_adverse_change": re.compile(
        r"\b(material[\s-]*adverse[\s-]*(change|effect|event)|MAC\b|MAE\b|materially[\s-]*adverse)\b",
        re.IGNORECASE,
    ),
    "closing_conditions": re.compile(
        r"\b(condition(s)?[\s-]*to[\s-]*(closing|completion|consummation)|condition[\s-]*precedent|closing[\s-]*condition)\b",
        re.IGNORECASE,
    ),
    "purchase_price_adjustment": re.compile(
        r"\b(purchase[\s-]*price[\s-]*adjustment|working[\s-]*capital[\s-]*adjustment|true[\s-]*up|locked[\s-]*box|completion[\s-]*accounts)\b",
        re.IGNORECASE,
    ),
    "earnout_mechanics": re.compile(r"\b(earn[\s-]*out|earnout|contingent[\s-]*consideration)\b", re.IGNORECASE),
    "basket_deductible": re.compile(
        r"\b(basket\b|deductible\b|tipping[\s-]*basket|true[\s-]*deductible)\b.{0,60}\bindemnif\b",
        re.IGNORECASE,
    ),
    "survival_period": re.compile(
        r"\b(survival[\s-]*(period|of[\s-]*representations?|clause)|representations?[\s-]*shall[\s-]*survive)\b",
        re.IGNORECASE,
    ),
}

METRIC_PATTERNS = {
    "revenue": re.compile(r"\b(revenue|sales)\b[^\n$]{0,80}\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?)(?:\s*(million|mm|m|billion|bn|b))?", re.IGNORECASE),
    "ebitda": re.compile(r"\b(adjusted\s+)?ebitda\b[^\n$]{0,80}\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?)(?:\s*(million|mm|m|billion|bn|b))?", re.IGNORECASE),
    "debt": re.compile(r"\b(debt|borrowings|loan balance)\b[^\n$]{0,80}\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?)(?:\s*(million|mm|m|billion|bn|b))?", re.IGNORECASE),
}

MULTIPLIERS = {
    None: 1.0,
    "m": 1_000_000.0,
    "mm": 1_000_000.0,
    "million": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
}

CLAUSE_META = {
    # ── Change of control group ──────────────────────────────────────────────
    "change_of_control": {
        "category": "contract",
        "severity": "high",
        "title": "Change-of-control clause detected",
        "description": "A change-of-control clause was identified and should be reviewed for transfer restrictions.",
        "recommendation": "Review assignment/consent requirements with counsel.",
        "confidence": 0.91,
    },
    "assignment_consent": {
        "category": "contract",
        "severity": "medium",
        "title": "Assignment/consent language detected",
        "description": "Assignment or consent constraints may require third-party approvals.",
        "recommendation": "List contracts requiring counterpart consent and map to closing conditions.",
        "confidence": 0.84,
    },
    "novation": {
        "category": "contract",
        "severity": "medium",
        "title": "Novation clause detected",
        "description": "Novation language indicates a contract may be substituted or transferred to a new party.",
        "recommendation": "Confirm whether novation requires counterparty consent and assess timing risk.",
        "confidence": 0.82,
    },
    "drag_along": {
        "category": "contract",
        "severity": "medium",
        "title": "Drag-along provision detected",
        "description": "Drag-along rights allow majority shareholders to compel minority shareholders to sell.",
        "recommendation": "Verify drag-along threshold, notice period, and price protections for minority.",
        "confidence": 0.88,
    },
    "tag_along": {
        "category": "contract",
        "severity": "low",
        "title": "Tag-along provision detected",
        "description": "Tag-along rights allow minority shareholders to join a majority sale on the same terms.",
        "recommendation": "Confirm tag-along scope and whether it applies to this transaction structure.",
        "confidence": 0.87,
    },
    # ── Customer / revenue group ─────────────────────────────────────────────
    "customer_contract": {
        "category": "commercial",
        "severity": "medium",
        "title": "Key customer contract detected",
        "description": "A master service agreement or key customer contract was identified.",
        "recommendation": "Review renewal terms, termination rights, and change-of-control provisions in each contract.",
        "confidence": 0.80,
    },
    "revenue_share": {
        "category": "commercial",
        "severity": "medium",
        "title": "Revenue sharing arrangement detected",
        "description": "Revenue share provisions may affect net margin and post-close financial projections.",
        "recommendation": "Extract revenue share percentages and assess impact on pro-forma EBITDA.",
        "confidence": 0.83,
    },
    "exclusivity": {
        "category": "commercial",
        "severity": "high",
        "title": "Exclusivity / sole-source clause detected",
        "description": "Exclusivity provisions may restrict the ability to engage alternative suppliers or customers post-close.",
        "recommendation": "Map exclusivity scope and duration; assess impact on growth strategy.",
        "confidence": 0.85,
    },
    "mfn_pricing": {
        "category": "commercial",
        "severity": "medium",
        "title": "Most Favoured Nation (MFN) pricing clause detected",
        "description": "MFN clauses require offering a counterparty the best pricing given to any other party.",
        "recommendation": "Identify MFN beneficiaries and assess margin compression risk at scale.",
        "confidence": 0.84,
    },
    "termination": {
        "category": "commercial",
        "severity": "medium",
        "title": "Termination-for-convenience clause detected",
        "description": "Contract can be terminated at will or upon notice without cause.",
        "recommendation": "Quantify revenue at risk per contract and assess notice period adequacy.",
        "confidence": 0.80,
    },
    "termination_penalty": {
        "category": "legal",
        "severity": "high",
        "title": "Termination penalty language detected",
        "description": "Termination provisions may include penalty/fee exposure.",
        "recommendation": "Quantify termination penalty scenarios and trigger conditions.",
        "confidence": 0.88,
    },
    # ── Debt / covenant group ────────────────────────────────────────────────
    "debt_covenant": {
        "category": "debt",
        "severity": "medium",
        "title": "Debt covenant language detected",
        "description": "Debt covenant references were found and may impact post-close flexibility.",
        "recommendation": "Extract covenant thresholds and test against current and projected financials.",
        "confidence": 0.80,
    },
    "leverage_ratio": {
        "category": "debt",
        "severity": "high",
        "title": "Leverage ratio covenant detected",
        "description": "A leverage ratio covenant restricts total debt relative to EBITDA.",
        "recommendation": "Extract the leverage threshold and test headroom under base, downside, and acquisition scenarios.",
        "confidence": 0.87,
    },
    "interest_coverage": {
        "category": "debt",
        "severity": "medium",
        "title": "Interest coverage / FCCR covenant detected",
        "description": "An interest coverage or fixed charge coverage ratio covenant limits debt service capacity.",
        "recommendation": "Test covenant headroom under projected EBITDA and rising rate scenarios.",
        "confidence": 0.84,
    },
    "event_of_default": {
        "category": "debt",
        "severity": "high",
        "title": "Event of default provision detected",
        "description": "Events of default (including cross-default) can trigger acceleration of debt obligations.",
        "recommendation": "List all events of default and cross-default triggers; confirm no current breach.",
        "confidence": 0.89,
    },
    "prepayment": {
        "category": "debt",
        "severity": "medium",
        "title": "Prepayment / call premium detected",
        "description": "Prepayment provisions may impose make-whole or call premium costs on early debt repayment.",
        "recommendation": "Quantify prepayment cost at expected hold period and refinancing scenarios.",
        "confidence": 0.82,
    },
    # ── IP group ─────────────────────────────────────────────────────────────
    "ip_assignment": {
        "category": "ip",
        "severity": "high",
        "title": "IP assignment clause detected",
        "description": "IP assignment provisions transfer ownership of intellectual property.",
        "recommendation": "Confirm direction of assignment (to company vs. from company) and scope of IP transferred.",
        "confidence": 0.85,
    },
    "license_terms": {
        "category": "ip",
        "severity": "medium",
        "title": "License grant detected",
        "description": "License provisions grant rights to use intellectual property.",
        "recommendation": "Review exclusivity, sublicensing rights, and field-of-use restrictions.",
        "confidence": 0.78,
    },
    "non_compete": {
        "category": "ip",
        "severity": "medium",
        "title": "Non-compete restriction detected",
        "description": "Non-compete clauses restrict parties from competing for a defined period and geography.",
        "recommendation": "Assess enforceability, geographic scope, and duration relative to deal strategy.",
        "confidence": 0.86,
    },
    "non_solicit": {
        "category": "ip",
        "severity": "low",
        "title": "Non-solicitation clause detected",
        "description": "Non-solicitation provisions restrict recruitment of employees or customers.",
        "recommendation": "Confirm scope (employees vs. customers), duration, and post-close applicability.",
        "confidence": 0.85,
    },
    # ── Employment group ─────────────────────────────────────────────────────
    "employment_term": {
        "category": "people",
        "severity": "medium",
        "title": "Key employment agreement detected",
        "description": "An employment agreement for key personnel was identified.",
        "recommendation": "Confirm contract term, notice period, and retention/rollover plan for key employees.",
        "confidence": 0.82,
    },
    "severance": {
        "category": "people",
        "severity": "medium",
        "title": "Severance / separation provision detected",
        "description": "Severance terms define payout obligations upon termination of key employees.",
        "recommendation": "Quantify total severance exposure and assess change-of-control acceleration triggers.",
        "confidence": 0.84,
    },
    "equity_vesting": {
        "category": "people",
        "severity": "medium",
        "title": "Equity vesting provision detected",
        "description": "Equity vesting terms affect management retention and dilution post-close.",
        "recommendation": "Map unvested equity by employee; assess acceleration on change of control.",
        "confidence": 0.83,
    },
    # ── SPA core group ───────────────────────────────────────────────────────
    "representations_warranties": {
        "category": "spa",
        "severity": "high",
        "title": "Representations & Warranties detected",
        "description": "R&W provisions define seller's factual assertions about the business that form the basis of deal pricing.",
        "recommendation": "Review R&W scope, any qualifications (knowledge, materiality), and R&W insurance applicability.",
        "confidence": 0.88,
    },
    "indemnification_cap": {
        "category": "spa",
        "severity": "high",
        "title": "Indemnification / liability provision detected",
        "description": "Indemnification provisions define remedies for R&W breaches; the cap limits total seller exposure.",
        "recommendation": "Extract indemnification cap, basket/deductible structure, and survival period for all rep categories.",
        "confidence": 0.90,
    },
    "material_adverse_change": {
        "category": "spa",
        "severity": "high",
        "title": "Material Adverse Change (MAC/MAE) clause detected",
        "description": "MAC/MAE provisions allow a buyer to walk away if a materially adverse event occurs before closing.",
        "recommendation": "Review MAC definition, carve-outs (pandemic, market-wide events), and buyer walk-away conditions.",
        "confidence": 0.87,
    },
    "closing_conditions": {
        "category": "spa",
        "severity": "medium",
        "title": "Conditions to closing detected",
        "description": "Closing conditions must be satisfied before the transaction can complete.",
        "recommendation": "List all unsatisfied closing conditions and assess timing/regulatory risk to close.",
        "confidence": 0.85,
    },
    "purchase_price_adjustment": {
        "category": "spa",
        "severity": "medium",
        "title": "Purchase price adjustment mechanism detected",
        "description": "Price adjustment mechanics (working capital, locked box) affect final deal consideration.",
        "recommendation": "Confirm adjustment mechanism, reference date, and any disagreement resolution process.",
        "confidence": 0.83,
    },
    "earnout_mechanics": {
        "category": "spa",
        "severity": "medium",
        "title": "Earnout provision detected",
        "description": "Earnout provisions tie a portion of deal consideration to future performance metrics.",
        "recommendation": "Extract earnout metric, period, cap, and any seller operating covenants during the earnout.",
        "confidence": 0.86,
    },
    "basket_deductible": {
        "category": "spa",
        "severity": "medium",
        "title": "Basket / deductible threshold detected",
        "description": "Indemnification basket/deductible sets a minimum loss threshold before claims can be made.",
        "recommendation": "Confirm basket type (tipping vs. true deductible), amount, and whether fundamental reps are excluded.",
        "confidence": 0.80,
    },
    "survival_period": {
        "category": "spa",
        "severity": "medium",
        "title": "Survival period for representations detected",
        "description": "Survival period determines how long after closing R&W claims can be brought.",
        "recommendation": "Note survival period by rep category (general reps vs. fundamental reps vs. tax reps).",
        "confidence": 0.82,
    },
}



def _row_dicts(rows: List[tuple]) -> List[dict]:
    out = []
    for document_id, filename, chunk_id, chunk_index, page_number, section_type, chunk_metadata, text in rows:
        raw = text or ""
        anchor_page, page_range = DocumentChunk.resolve_page_info(chunk_metadata, page_number)
        out.append(
            {
                "document_id": document_id,
                "filename": filename or "",
                "chunk_id": str(chunk_id) if chunk_id is not None else None,
                "chunk_index": chunk_index,
                "page_number": anchor_page,
                "page_range": page_range,
                "section_type": section_type,
                "text": raw,
                "text_lower": raw.lower(),
            }
        )
    return out


def _clip_quote(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].strip().replace("\n", " ")


def _make_evidence(
    *,
    row: dict,
    start: Optional[int],
    end: Optional[int],
    quote: str,
    confidence: Optional[float],
    metadata: Optional[dict] = None,
) -> dict:
    metadata_json = dict(metadata or {})
    if row.get("page_range"):
        metadata_json.setdefault("source_page_range", row["page_range"])
    return {
        "source_document_id": row["document_id"],
        "source_chunk_id": row["chunk_id"],
        "source_page_number": row["page_number"],
        "char_start": start,
        "char_end": end,
        "quote": quote[:1000],
        "confidence": confidence,
        "metadata_json": metadata_json,
    }


def _extract_clause_hits(rows: List[dict]) -> List[dict]:
    hits = []
    for row in rows:
        text = row["text"]
        for clause_type, pattern in CLAUSE_PATTERNS.items():
            for match in pattern.finditer(text):
                start, end = match.span()
                quote = _clip_quote(text, start, end)
                hits.append(
                    {
                        "clause_type": clause_type,
                        "evidence": _make_evidence(
                            row=row,
                            start=start,
                            end=end,
                            quote=quote,
                            confidence=CLAUSE_META[clause_type]["confidence"],
                            metadata={"clause_type": clause_type, "engine": "regex_v1"},
                        ),
                    }
                )
                break
    return hits


def _normalize_numeric(value_text: str, unit_text: Optional[str]) -> Optional[float]:
    try:
        base = float(value_text.replace(",", ""))
    except Exception:
        return None
    mult = MULTIPLIERS.get((unit_text or "").strip().lower() or None, 1.0)
    return base * mult


def _extract_numeric_signals(rows: List[dict]) -> Dict[str, List[dict]]:
    signals: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        text = row["text"]
        for metric, pattern in METRIC_PATTERNS.items():
            for match in pattern.finditer(text):
                span = match.span()
                value_text = match.group(2)
                unit_text = match.group(3)
                value = _normalize_numeric(value_text, unit_text)
                if value is None:
                    continue
                quote = _clip_quote(text, span[0], span[1])
                signals[metric].append(
                    {
                        "value": value,
                        "evidence": _make_evidence(
                            row=row,
                            start=span[0],
                            end=span[1],
                            quote=quote,
                            confidence=0.76,
                            metadata={"metric": metric, "unit": (unit_text or "").lower(), "engine": "regex_numeric_v1"},
                        ),
                    }
                )
    return signals


def _build_numeric_reconciliation_findings(signals: Dict[str, List[dict]]) -> List[dict]:
    findings = []
    for metric, rows in signals.items():
        values = [r["value"] for r in rows]
        if len(values) < 2:
            continue
        hi = max(values)
        lo = min(values)
        if lo <= 0:
            continue
        spread = hi / lo
        if spread >= 1.35:
            findings.append(
                {
                    "category": "numeric_reconciliation",
                    "severity": "high" if spread >= 2.0 else "medium",
                    "title": f"Inconsistent {metric} values detected",
                    "description": f"Extracted {metric} values vary significantly across documents/chunks.",
                    "recommendation": f"Reconcile {metric} definitions (GAAP/non-GAAP, period, pro-forma) before IC.",
                    "status": "open",
                    "source_document_id": rows[0]["evidence"]["source_document_id"],
                    "source_chunk_id": rows[0]["evidence"]["source_chunk_id"],
                    "source_page_number": rows[0]["evidence"]["source_page_number"],
                    "evidence_quote": rows[0]["evidence"]["quote"],
                    "confidence": 0.79,
                    "metadata_json": {
                        "engine": "numeric_recon_v1",
                        "metric": metric,
                        "min_value": lo,
                        "max_value": hi,
                        "spread_ratio": round(spread, 3),
                    },
                    "evidence_list": [r["evidence"] for r in rows[:4]],
                }
            )

    revenue_vals = [r["value"] for r in signals.get("revenue", [])]
    ebitda_vals = [r["value"] for r in signals.get("ebitda", [])]
    if revenue_vals and ebitda_vals:
        if median(ebitda_vals) > median(revenue_vals):
            base_ev = signals["ebitda"][0]["evidence"]
            findings.append(
                {
                    "category": "numeric_reconciliation",
                    "severity": "high",
                    "title": "EBITDA exceeds Revenue sanity check",
                    "description": "Extracted median EBITDA is greater than median Revenue, indicating potential parsing or definition mismatch.",
                    "recommendation": "Verify units and period alignment for revenue/EBITDA table fields.",
                    "status": "open",
                    "source_document_id": base_ev["source_document_id"],
                    "source_chunk_id": base_ev["source_chunk_id"],
                    "source_page_number": base_ev["source_page_number"],
                    "evidence_quote": base_ev["quote"],
                    "confidence": 0.87,
                    "metadata_json": {
                        "engine": "numeric_recon_v1",
                        "revenue_median": median(revenue_vals),
                        "ebitda_median": median(ebitda_vals),
                    },
                    "evidence_list": [base_ev],
                }
            )
    return findings


def _build_checklist(
    rows: List[dict],
    clause_hits: List[dict],
    numeric_signals: Dict[str, List[dict]],
    document_classifications: Optional[Dict[str, dict]] = None,
    llm_financials: Optional[dict] = None,
    structured_clauses_by_type: Optional[Dict[str, List[dict]]] = None,
) -> List[dict]:
    """Rules-driven checklist matching using CHECKLIST_RULES map."""
    by_doc: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        by_doc[row["document_id"]].append(row)

    # Build sets for fast lookup
    found_clause_types: set = {h["clause_type"] for h in clause_hits}
    # Also count structured clauses if available
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

        # 1. Check clause types (exact match → "covered")
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

        # 2. Check numeric signals (→ "covered")
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

        # 3. Check document classifications (→ "covered")
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

        # 4. Check LLM financials (→ "covered")
        if status == "missing" and rules.get("check_llm_financials") and llm_financials:
            if llm_financials.get("historical") or llm_financials.get("ratios"):
                status = "covered"
                confidence = rules.get("base_confidence", 0.82)

        # 5. Check full-match keywords in text (→ "covered" or "partial")
        if status == "missing":
            full_keywords = rules.get("keywords") or []
            partial_keywords = rules.get("partial_keywords") or []
            for doc_id, chunk_rows in by_doc.items():
                for row in chunk_rows:
                    text_lower = row["text_lower"]
                    matched_kw = next((kw for kw in full_keywords if kw in text_lower), None)
                    if matched_kw:
                        idx = text_lower.find(matched_kw)
                        ev = _make_evidence(
                            row=row,
                            start=idx,
                            end=idx + len(matched_kw),
                            quote=_clip_quote(row["text"], idx, idx + len(matched_kw)),
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
                    # Partial match — only if no full keywords defined
                    if not full_keywords and partial_keywords:
                        matched_pkw = next((kw for kw in partial_keywords if kw in text_lower), None)
                        if matched_pkw:
                            idx = text_lower.find(matched_pkw)
                            ev = _make_evidence(
                                row=row,
                                start=idx,
                                end=idx + len(matched_pkw),
                                quote=_clip_quote(row["text"], idx, idx + len(matched_pkw)),
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


def _enrich_finding_from_structured_clause(
    finding: dict,
    structured_clauses_by_type: Dict[str, List[dict]],
) -> dict:
    """Append quantified field values from LLM-extracted structured clause to finding description."""
    clause_type = (finding.get("metadata_json") or {}).get("clause_type")
    if not clause_type:
        return finding
    clauses = structured_clauses_by_type.get(clause_type, [])
    if not clauses:
        return finding

    best = clauses[0]
    fields = best.get("extracted_fields") or {}
    enrichments = []

    # SPA-specific fields
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
        carveouts = fields["mac_carveouts"][:3]
        enrichments.append(f"MAC carveouts: {', '.join(carveouts)}")
    if fields.get("adjustment_mechanism"):
        enrichments.append(f"Price adj: {fields['adjustment_mechanism']}")

    # General clause fields
    if fields.get("threshold"):
        enrichments.append(f"Threshold: {fields['threshold']}")
    if fields.get("consent_required") is True and fields.get("consent_parties"):
        parties = ", ".join(fields["consent_parties"][:3])
        enrichments.append(f"Consent: {parties}")
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
    # Add LLM interpretation if available
    interpretation = best.get("interpretation")
    if interpretation:
        finding["metadata_json"] = {**finding.get("metadata_json", {}), "llm_interpretation": interpretation}
    return finding


def _detect_missing_clauses(
    clause_hits: List[dict],
    document_classifications: Dict[str, dict],
    rows: List[dict],
) -> List[dict]:
    """Generate findings for expected clauses absent from classified documents."""
    # Build per-document set of found clause types
    found_by_doc: Dict[str, set] = defaultdict(set)
    for hit in clause_hits:
        doc_id = hit["evidence"]["source_document_id"]
        found_by_doc[doc_id].add(hit["clause_type"])

    # Build doc_id → filename map
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


def _build_findings(
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
        # Enrich with quantified fields from LLM-structured clause (step 3)
        finding = _enrich_finding_from_structured_clause(finding, sc_by_type)
        findings.append(finding)

    # Commercial concentration risk hook
    for row in rows:
        text_norm = row["text_lower"]
        if "customer concentration" in text_norm:
            idx = text_norm.find("customer concentration")
            ev = _make_evidence(
                row=row,
                start=idx,
                end=idx + len("customer concentration"),
                quote=_clip_quote(row["text"], idx, idx + len("customer concentration")),
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

    # Extend with numeric reconciliation findings
    findings.extend(numeric_findings)

    # Add missing clause findings (step 4)
    if document_classifications:
        missing = _detect_missing_clauses(clause_hits, document_classifications, rows)
        findings.extend(missing)

    return findings[:25]


def _build_summary(
    room_name: str,
    checklist_entries: List[dict],
    finding_entries: List[dict],
    document_classifications: Dict[str, dict],
    verification_stats: Dict[str, int],
) -> Dict[str, Any]:
    checklist_items = [entry["item"] for entry in checklist_entries]
    findings = finding_entries
    covered = sum(1 for item in checklist_items if item["status"] in {"covered", "partial"})
    total = len(checklist_items)
    completion = 0.0 if total == 0 else round(covered * 100.0 / total, 2)
    high = sum(1 for f in findings if f["severity"] == "high")
    medium = sum(1 for f in findings if f["severity"] == "medium")
    low = sum(1 for f in findings if f["severity"] == "low")

    doc_type_counts = defaultdict(int)
    for row in document_classifications.values():
        doc_type_counts[row.get("document_type") or "other"] += 1

    markdown = "\n".join(
        [
            f"# Diligence Overview - {room_name}",
            "",
            f"- Checklist coverage: **{covered}/{total}** ({completion}%)",
            f"- Findings: **{len(findings)}** (High: {high}, Medium: {medium}, Low: {low})",
            f"- Verification: **{verification_stats.get('verified', 0)} verified**, **{verification_stats.get('needs_review', 0)} needs review**",
            f"- Document types detected: {dict(doc_type_counts)}",
            "",
            "## Priority Risks",
            f"1. High severity findings detected: **{high}**",
            "2. Validate covenant flexibility and change-of-control constraints.",
            "3. Reconcile numeric discrepancies before investment committee memo.",
            "",
            "## Suggested Management Questions",
            "1. Provide covenant headroom calculations under base and downside case.",
            "2. Break out top-10 customer revenue by month and churn trend.",
            "3. Identify all contracts requiring consent on change-of-control.",
        ]
    )

    citations = []
    for finding in findings[:5]:
        ev = (finding.get("evidence_list") or [None])[0]
        citations.append(
            {
                "entity": finding["title"],
                "document_id": ev.get("source_document_id") if ev else None,
                "page_number": ev.get("source_page_number") if ev else None,
                "quote": (ev.get("quote") if ev else finding.get("evidence_quote"))[:220],
                "confidence": ev.get("confidence") if ev else finding.get("confidence"),
            }
        )

    summary_evidence = [f["evidence_list"][0] for f in findings if f.get("evidence_list")][:5]
    return {
        "markdown": markdown,
        "citations": citations,
        "confidence": 0.78,
        "evidence_list": summary_evidence,
        "metadata": {
            "document_classification": document_classifications,
            "verification": verification_stats,
        },
    }


def _build_document_classification_summary(document_classifications: Dict[str, dict]) -> Dict[str, Any]:
    doc_type_counts: Dict[str, int] = defaultdict(int)
    needs_review = 0
    for row in document_classifications.values():
        doc_type = row.get("document_type") or "other"
        doc_type_counts[doc_type] += 1
        if row.get("needs_review"):
            needs_review += 1
    return {
        "total": len(document_classifications),
        "needs_review": needs_review,
        "document_type_counts": dict(doc_type_counts),
    }


@shared_task(bind=True)
def run_diligence_analysis_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    room_id = payload["room_id"]
    run_id = payload["analysis_run_id"]
    user_id = payload["user_id"]

    db = SessionLocal()
    repo = PEDiligenceRepository(db)

    try:
        repo.update_analysis_run(
            run_id=run_id,
            status="running",
            current_stage="load_documents",
            progress_percent=10,
            started_at=datetime.utcnow(),
        )
        row_data = _row_dicts(repo.get_room_documents_and_chunks(room_id=room_id))

        repo.update_analysis_run(
            run_id=run_id,
            current_stage="document_classification",
            progress_percent=20,
        )
        document_classifications = classify_documents(row_data)
        llm_rejections: List[dict] = []
        if settings.pe_diligence_classifier_llm_fallback_enabled:
            low_conf_inputs = build_low_confidence_inputs(
                row_data,
                document_classifications,
                max_chars_per_doc=settings.pe_diligence_classifier_llm_input_chars,
            )
            if low_conf_inputs:
                try:
                    adapter = PEDiligenceClassificationAdapter()
                    llm_candidates = asyncio.run(adapter.classify_low_confidence(low_conf_inputs))
                    document_classifications, llm_rejections = apply_llm_fallback(
                        document_classifications,
                        llm_candidates,
                        min_override_confidence=settings.pe_diligence_classifier_llm_min_confidence,
                    )
                except Exception as llm_exc:
                    logger.warning(
                        "PE diligence LLM classification fallback failed; continuing with rule-based output",
                        extra={"room_id": room_id, "run_id": run_id, "error": str(llm_exc)},
                    )
        for rejected in llm_rejections:
            repo.add_audit_event(
                room_id=room_id,
                analysis_run_id=run_id,
                actor_user_id=user_id,
                event_type="analysis.classification_candidate_rejected",
                entity_type="room_document",
                entity_id=rejected.get("document_id"),
                payload={
                    "reason_code": rejected.get("reason_code"),
                    "expected_rule_anchor_id": rejected.get("expected_rule_anchor_id"),
                    "candidate_rule_anchor_id": rejected.get("candidate_rule_anchor_id"),
                    "candidate_confidence": rejected.get("candidate_confidence"),
                },
            )
        classification_summary = _build_document_classification_summary(document_classifications)
        for doc_id, classification in document_classifications.items():
            repo.update_room_document_metadata(
                room_id=room_id,
                document_id=doc_id,
                ingest_status="classified",
                metadata_patch={"document_classification": classification},
            )
        repo.update_analysis_run(
            run_id=run_id,
            metadata_patch={
                "document_classification": document_classifications,
                "document_classification_summary": classification_summary,
            },
        )

        # Build per-document filename and text-head maps for amendment linker
        _max_link_chars = settings.pe_diligence_amendment_linking_input_chars
        _doc_filename_map: Dict[str, str] = {}
        _doc_text_head: Dict[str, str] = {}
        for _row in row_data:
            _did = _row["document_id"]
            if _row.get("filename") and _did not in _doc_filename_map:
                _doc_filename_map[_did] = _row["filename"]
            if _did not in _doc_text_head:
                _doc_text_head[_did] = (_row.get("text") or "")[:_max_link_chars]
            elif len(_doc_text_head[_did]) < _max_link_chars:
                _doc_text_head[_did] = (
                    _doc_text_head[_did] + "\n" + (_row.get("text") or "")
                )[:_max_link_chars]

        room_doc_list = [
            {"document_id": doc_id, "filename": _doc_filename_map.get(doc_id, "")}
            for doc_id in document_classifications
        ]

        repo.update_analysis_run(
            run_id=run_id,
            current_stage="amendment_linking",
            progress_percent=25,
        )

        if settings.pe_diligence_amendment_linking_enabled:
            amendment_docs = [
                {
                    "document_id": doc_id,
                    "filename": _doc_filename_map.get(doc_id, ""),
                    "text": _doc_text_head.get(doc_id, ""),
                }
                for doc_id, cls in document_classifications.items()
                if cls.get("document_type") == "amendment"
            ]
            if amendment_docs:
                try:
                    from app.verticals.private_equity.diligence.amendment_linker import PEDiligenceAmendmentLinker
                    linker = PEDiligenceAmendmentLinker()
                    link_results = asyncio.run(linker.link_amendments(
                        amendments=amendment_docs,
                        room_documents=room_doc_list,
                    ))
                    for doc_id, candidate in link_results.items():
                        repo.update_room_document_metadata(
                            room_id=room_id,
                            document_id=doc_id,
                            metadata_patch={"amendment_link": candidate.model_dump()},
                        )
                    for doc_id, candidate in link_results.items():
                        repo.add_audit_event(
                            room_id=room_id,
                            analysis_run_id=run_id,
                            actor_user_id=user_id,
                            event_type="amendment.linked" if candidate.parent_document_id else "amendment.unlinked",
                            entity_type="room_document",
                            entity_id=doc_id,
                            payload=candidate.model_dump(),
                        )
                except Exception as link_exc:
                    logger.warning(
                        "Amendment linking failed; continuing without amendment links",
                        extra={"room_id": room_id, "run_id": run_id, "error": str(link_exc)[:300]},
                    )

        repo.update_analysis_run(
            run_id=run_id,
            current_stage="clause_extraction",
            progress_percent=30,
        )
        clause_hits = _extract_clause_hits(row_data)

        # Stage 4b: LLM structured clause extraction (opt-in)
        structured_clauses_by_type: Dict[str, List[dict]] = {}
        if settings.pe_diligence_llm_clause_extraction_enabled:
            repo.update_analysis_run(
                run_id=run_id,
                current_stage="llm_clause_extraction",
                progress_percent=38,
            )
            try:
                from app.verticals.private_equity.diligence.clause_extractor import LLMClauseExtractor
                extractor = LLMClauseExtractor()
                playbooks = repo.get_playbooks_for_extraction()
                # Extract unique document IDs from row_data (already done above for numeric, reuse)
                if "room_document_ids" not in locals():
                    room_document_ids = list(set(row["document_id"] for row in row_data if row.get("document_id")))
                if playbooks:
                    structured_clauses = asyncio.run(
                        extractor.extract_all(
                            clause_hits=clause_hits,
                            playbooks=playbooks,
                            db=db,
                            document_ids=room_document_ids,
                            room_id=room_id,
                            run_id=run_id,
                        )
                    )
                    if structured_clauses:
                        repo.save_clauses(room_id=room_id, run_id=run_id, clauses=structured_clauses)
                        logger.info(
                            "LLM clause extraction saved",
                            extra={"room_id": room_id, "run_id": run_id, "count": len(structured_clauses)},
                        )
                        # Index by clause_type for downstream enrichment
                        for c in structured_clauses:
                            structured_clauses_by_type.setdefault(c["clause_type"], []).append(c)
            except Exception as clause_exc:
                logger.warning(
                    "LLM clause extraction stage failed; continuing",
                    extra={"room_id": room_id, "run_id": run_id, "error": str(clause_exc)[:300]},
                )

        repo.update_analysis_run(
            run_id=run_id,
            current_stage="numeric_reconciliation",
            progress_percent=48,
        )
        numeric_signals = _extract_numeric_signals(row_data)
        numeric_findings = _build_numeric_reconciliation_findings(numeric_signals)

        # Stage 5b: LLM numeric extraction (opt-in)
        llm_financials: Optional[dict] = None
        if settings.pe_diligence_llm_numeric_extraction_enabled:
            repo.update_analysis_run(
                run_id=run_id,
                current_stage="llm_numeric_extraction",
                progress_percent=55,
            )
            try:
                from app.verticals.private_equity.diligence.numeric_extractor import LLMNumericExtractor
                # Extract unique document IDs from row_data
                room_document_ids = list(set(row["document_id"] for row in row_data if row.get("document_id")))
                llm_financials = asyncio.run(
                    LLMNumericExtractor().extract(
                        db=db,
                        document_ids=room_document_ids,
                        document_classifications=document_classifications,
                        room_id=room_id,
                        run_id=run_id,
                    )
                )
                if llm_financials:
                    repo.update_analysis_run(
                        run_id=run_id,
                        metadata_patch={"llm_financials": llm_financials},
                    )
                    logger.info(
                        "LLM numeric extraction complete",
                        extra={"room_id": room_id, "run_id": run_id},
                    )
            except Exception as num_exc:
                logger.warning(
                    "LLM numeric extraction failed; continuing",
                    extra={"room_id": room_id, "run_id": run_id, "error": str(num_exc)[:300]},
                )

        repo.update_analysis_run(
            run_id=run_id,
            current_stage="checklist_mapping",
            progress_percent=65,
        )
        checklist_entries = _build_checklist(
            row_data,
            clause_hits,
            numeric_signals,
            document_classifications=document_classifications,
            llm_financials=llm_financials,
            structured_clauses_by_type=structured_clauses_by_type,
        )
        checklist_rows = repo.replace_checklist_items(
            room_id=room_id,
            items=[entry["item"] for entry in checklist_entries],
        )

        repo.update_analysis_run(
            run_id=run_id,
            current_stage="risk_scoring",
            progress_percent=72,
        )
        finding_entries = _build_findings(
            row_data,
            clause_hits,
            numeric_findings,
            structured_clauses_by_type=structured_clauses_by_type,
            document_classifications=document_classifications,
        )

        # Stage 7: LLM findings synthesis (opt-in) — replaces rule-based findings
        if settings.pe_diligence_llm_findings_synthesis_enabled:
            repo.update_analysis_run(
                run_id=run_id,
                current_stage="llm_findings_synthesis",
                progress_percent=78,
            )
            try:
                from app.verticals.private_equity.diligence.findings_synthesizer import LLMFindingsSynthesizer
                synthesized = asyncio.run(
                    LLMFindingsSynthesizer().synthesize(
                        clause_hits=clause_hits,
                        structured_clauses_by_type=structured_clauses_by_type,
                        numeric_signals=numeric_signals,
                        llm_financials=llm_financials,
                        checklist_entries=checklist_entries,
                        document_classifications=document_classifications,
                        room_id=room_id,
                        run_id=run_id,
                    )
                )
                if synthesized:
                    finding_entries = synthesized
                    logger.info(
                        "LLM findings synthesis complete",
                        extra={"room_id": room_id, "run_id": run_id, "count": len(synthesized)},
                    )
            except Exception as synth_exc:
                logger.warning(
                    "LLM findings synthesis failed; using rule-based findings",
                    extra={"room_id": room_id, "run_id": run_id, "error": str(synth_exc)[:300]},
                )

        repo.update_analysis_run(
            run_id=run_id,
            current_stage="verification",
            progress_percent=86,
        )
        verified_finding_entries, verification_stats = verify_findings(finding_entries)
        repo.update_analysis_run(
            run_id=run_id,
            metadata_patch={"verification": verification_stats},
        )

        finding_rows_payload = []
        for entry in verified_finding_entries:
            clean = {k: v for k, v in entry.items() if k != "evidence_list"}
            finding_rows_payload.append(clean)
        finding_rows = repo.replace_findings(
            room_id=room_id,
            run_id=run_id,
            findings=finding_rows_payload,
        )

        repo.update_analysis_run(
            run_id=run_id,
            current_stage="summary_generation",
            progress_percent=90,
        )
        room = repo.get_room(room_id=room_id, org_id=payload["org_id"], user_id=user_id)
        summary_payload = _build_summary(
            room.name if room else "Diligence Room",
            checklist_entries,
            verified_finding_entries,
            document_classifications,
            verification_stats,
        )
        summary_engine = "summary_v2"

        # Stage 9: LLM summary generation (opt-in) — replaces template summary
        if settings.pe_diligence_llm_summary_generation_enabled:
            repo.update_analysis_run(
                run_id=run_id,
                current_stage="llm_summary",
                progress_percent=92,
            )
            try:
                from app.verticals.private_equity.diligence.summary_generator import LLMSummaryGenerator
                llm_summary = asyncio.run(
                    LLMSummaryGenerator().generate(
                        room_name=room.name if room else "Diligence Room",
                        finding_entries=verified_finding_entries,
                        checklist_entries=checklist_entries,
                        document_classifications=document_classifications,
                        verification_stats=verification_stats,
                        llm_financials=llm_financials,
                        structured_clauses_by_type=structured_clauses_by_type,
                        room_id=room_id,
                        run_id=run_id,
                    )
                )
                if llm_summary:
                    summary_payload = llm_summary
                    summary_engine = "llm_summary_v1"
                    logger.info(
                        "LLM summary generation complete",
                        extra={"room_id": room_id, "run_id": run_id},
                    )
            except Exception as sum_exc:
                logger.warning(
                    "LLM summary generation failed; using template summary",
                    extra={"room_id": room_id, "run_id": run_id, "error": str(sum_exc)[:300]},
                )

        summary_row = repo.upsert_summary(
            room_id=room_id,
            run_id=run_id,
            summary_type="diligence_overview",
            status="ready",
            content_markdown=summary_payload["markdown"],
            citations=summary_payload["citations"],
            confidence=summary_payload["confidence"],
            metadata={"engine": summary_engine, **summary_payload.get("metadata", {})},
            actor_user_id=user_id,
        )

        # Persist normalized evidence spans for checklist, findings, and summary.
        evidence_spans = []
        for entry, item_row in zip(checklist_entries, checklist_rows):
            for ev in entry.get("evidence", []):
                evidence_spans.append(
                    {
                        **ev,
                        "entity_type": "checklist_item",
                        "entity_id": item_row.id,
                    }
                )
        for entry, finding_row in zip(verified_finding_entries, finding_rows):
            for ev in entry.get("evidence_list", []):
                evidence_spans.append(
                    {
                        **ev,
                        "entity_type": "finding",
                        "entity_id": finding_row.id,
                    }
                )
        for ev in summary_payload.get("evidence_list", []):
            evidence_spans.append(
                {
                    **ev,
                    "entity_type": "summary",
                    "entity_id": summary_row.id,
                }
            )
        repo.replace_evidence_spans(
            room_id=room_id,
            run_id=run_id,
            spans=evidence_spans,
        )

        repo.update_analysis_run(
            run_id=run_id,
            status="completed",
            current_stage="completed",
            progress_percent=100,
            completed_at=datetime.utcnow(),
            metadata_patch={
                "verification": verification_stats,
                "document_classification_summary": classification_summary,
            },
        )
        repo.mark_room_status(room_id=room_id, status="completed", last_analyzed_at=datetime.utcnow())
        repo.add_audit_event(
            room_id=room_id,
            analysis_run_id=run_id,
            actor_user_id=user_id,
            event_type="analysis.completed",
            entity_type="analysis_run",
            entity_id=run_id,
            payload={
                "checklist_items": len(checklist_rows),
                "findings": len(finding_rows),
                "evidence_spans": len(evidence_spans),
                "clause_hits": len(clause_hits),
                "numeric_signals": {k: len(v) for k, v in numeric_signals.items()},
                "verification": verification_stats,
                "document_classification": {k: v.get("document_type") for k, v in document_classifications.items()},
            },
        )
        return {"status": "completed", "analysis_run_id": run_id}

    except Exception as exc:
        logger.exception("PE diligence analysis task failed", extra={"room_id": room_id, "run_id": run_id})
        repo.update_analysis_run(
            run_id=run_id,
            status="failed",
            current_stage="failed",
            progress_percent=100,
            error_message=str(exc)[:1000],
            completed_at=datetime.utcnow(),
        )
        repo.mark_room_status(room_id=room_id, status="failed")
        repo.add_audit_event(
            room_id=room_id,
            analysis_run_id=run_id,
            actor_user_id=user_id,
            event_type="analysis.failed",
            entity_type="analysis_run",
            entity_id=run_id,
            payload={"error": str(exc)[:1000]},
        )
        return {"status": "failed", "analysis_run_id": run_id, "error": str(exc)}
    finally:
        db.close()










