"""Canonical PE diligence document taxonomy and shared helpers."""
from __future__ import annotations

from enum import Enum
from typing import Iterable


class PEDocumentType(str, Enum):
    AMENDMENT = "amendment"
    OFFERING_MEMORANDUM = "offering_memorandum"
    PURCHASE_AGREEMENT = "purchase_agreement"
    MERGER_AGREEMENT = "merger_agreement"
    DISCLOSURE_SCHEDULE = "disclosure_schedule"
    SHAREHOLDER_AGREEMENT = "shareholder_agreement"
    FINANCIAL_STATEMENT = "financial_statement"
    QOE_REPORT = "qoe_report"
    EMPLOYMENT_AGREEMENT = "employment_agreement"
    IP_LICENSE = "ip_license"
    CUSTOMER_CONTRACT = "customer_contract"
    VENDOR_CONTRACT = "vendor_contract"
    NDA = "nda"
    TAX_DOCUMENT = "tax_document"
    REGULATORY_FILING = "regulatory_filing"
    INSURANCE_DOCUMENT = "insurance_document"
    CHARTER_DOCUMENT = "charter_document"
    POLICY_DOCUMENT = "policy_document"
    LEGAL_CONTRACT = "legal_contract"
    OTHER = "other"


def _values(items: Iterable[PEDocumentType]) -> tuple[str, ...]:
    return tuple(item.value for item in items)


ALL_DOC_TYPES = tuple(PEDocumentType)
ALL_DOC_TYPE_VALUES = _values(ALL_DOC_TYPES)
ALL_DOC_TYPE_VALUE_SET = frozenset(ALL_DOC_TYPE_VALUES)

DEFAULT_DOC_TYPE = PEDocumentType.OTHER.value
GENERIC_DOC_TYPES = frozenset({
    PEDocumentType.LEGAL_CONTRACT.value,
    PEDocumentType.OTHER.value,
})

TRANSACTION_DOC_TYPES = _values((
    PEDocumentType.PURCHASE_AGREEMENT,
    PEDocumentType.MERGER_AGREEMENT,
    PEDocumentType.DISCLOSURE_SCHEDULE,
    PEDocumentType.AMENDMENT,
))

FINANCIAL_DOC_TYPES = frozenset({
    PEDocumentType.FINANCIAL_STATEMENT.value,
    PEDocumentType.QOE_REPORT.value,
})

NUMERIC_EXTRACTION_DOC_TYPES = frozenset({
    PEDocumentType.FINANCIAL_STATEMENT.value,
    PEDocumentType.QOE_REPORT.value,
    PEDocumentType.OFFERING_MEMORANDUM.value,
})

CONTRACTUAL_DOC_TYPES = frozenset({
    PEDocumentType.PURCHASE_AGREEMENT.value,
    PEDocumentType.MERGER_AGREEMENT.value,
    PEDocumentType.DISCLOSURE_SCHEDULE.value,
    PEDocumentType.SHAREHOLDER_AGREEMENT.value,
    PEDocumentType.EMPLOYMENT_AGREEMENT.value,
    PEDocumentType.IP_LICENSE.value,
    PEDocumentType.CUSTOMER_CONTRACT.value,
    PEDocumentType.VENDOR_CONTRACT.value,
    PEDocumentType.NDA.value,
    PEDocumentType.LEGAL_CONTRACT.value,
    PEDocumentType.AMENDMENT.value,
    PEDocumentType.CHARTER_DOCUMENT.value,
})

HIGH_VALUE_CONTRACT_DOC_TYPES = frozenset({
    PEDocumentType.PURCHASE_AGREEMENT.value,
    PEDocumentType.MERGER_AGREEMENT.value,
    PEDocumentType.DISCLOSURE_SCHEDULE.value,
    PEDocumentType.SHAREHOLDER_AGREEMENT.value,
    PEDocumentType.CUSTOMER_CONTRACT.value,
    PEDocumentType.VENDOR_CONTRACT.value,
    PEDocumentType.IP_LICENSE.value,
    PEDocumentType.EMPLOYMENT_AGREEMENT.value,
    PEDocumentType.LEGAL_CONTRACT.value,
    PEDocumentType.AMENDMENT.value,
})

GENERIC_LLM_REVIEW_DOC_TYPES = GENERIC_DOC_TYPES


DOC_TYPE_METADATA: dict[str, dict] = {
    PEDocumentType.AMENDMENT.value: {
        "label": "Amendment",
        "patterns": (
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
        ),
        "type_weight": 1.1,
    },
    PEDocumentType.OFFERING_MEMORANDUM.value: {
        "label": "Offering Memorandum",
        "patterns": (
            "offering memorandum",
            "confidential information memorandum",
            "confidential investment memorandum",
            "cim",
            "investment highlights",
            "executive summary",
            "property overview",
            "business overview",
            "market opportunity",
            "growth strategy",
            "competitive landscape",
            "company overview",
        ),
        "type_weight": 1.0,
    },
    PEDocumentType.PURCHASE_AGREEMENT.value: {
        "label": "Purchase Agreement",
        "patterns": (
            "purchase agreement",
            "share purchase agreement",
            "stock purchase agreement",
            "asset purchase agreement",
            "membership interest purchase agreement",
            "purchase and sale agreement",
            "asset purchase",
            "stock purchase",
            "seller",
            "buyer",
            "representations and warranties",
        ),
        "type_weight": 1.25,
    },
    PEDocumentType.MERGER_AGREEMENT.value: {
        "label": "Merger Agreement",
        "patterns": (
            "agreement and plan of merger",
            "plan of merger",
            "merger sub",
            "surviving corporation",
            "merger consideration",
            "certificate of merger",
            "effective time of the merger",
            "merger agreement",
            "merger shall become effective",
            "acquisition agreement",
        ),
        "type_weight": 1.25,
    },
    PEDocumentType.DISCLOSURE_SCHEDULE.value: {
        "label": "Disclosure Schedule",
        "patterns": (
            "disclosure schedule",
            "disclosure schedules",
            "schedule of exceptions",
            "disclosure letter",
            "company disclosure letter",
            "seller disclosure letter",
        ),
        "type_weight": 1.15,
    },
    PEDocumentType.SHAREHOLDER_AGREEMENT.value: {
        "label": "Shareholder Agreement",
        "patterns": (
            "shareholders agreement",
            "shareholder agreement",
            "stockholders agreement",
            "stockholder agreement",
            "investors rights agreement",
            "registration rights agreement",
            "voting agreement",
            "right of first refusal",
            "co-sale agreement",
            "drag-along",
            "tag-along",
        ),
        "type_weight": 1.15,
    },
    PEDocumentType.FINANCIAL_STATEMENT.value: {
        "label": "Financial Statement",
        "patterns": (
            "balance sheet",
            "income statement",
            "cash flow",
            "statement of operations",
            "audited financial statements",
            "statement of financial position",
        ),
        "type_weight": 1.05,
    },
    PEDocumentType.QOE_REPORT.value: {
        "label": "QoE Report",
        "patterns": (
            "quality of earnings",
            "qoe",
            "adjusted ebitda",
            "normalization",
            "earnings adjustments",
        ),
        "type_weight": 1.05,
    },
    PEDocumentType.EMPLOYMENT_AGREEMENT.value: {
        "label": "Employment Agreement",
        "patterns": (
            "employment agreement",
            "employment contract",
            "base salary",
            "severance",
            "at-will",
            "annual bonus",
            "executive employment",
            "offer letter",
            "compensation agreement",
            "non-solicitation of employees",
        ),
        "type_weight": 1.15,
    },
    PEDocumentType.IP_LICENSE.value: {
        "label": "IP License",
        "patterns": (
            "license agreement",
            "licensor",
            "licensee",
            "royalty",
            "software license",
            "patent license",
            "technology license",
            "license grant",
            "intellectual property license",
            "collaboration and license agreement",
            "commercialization and license agreement",
        ),
        "type_weight": 1.15,
    },
    PEDocumentType.CUSTOMER_CONTRACT.value: {
        "label": "Customer Contract",
        "patterns": (
            "master services agreement",
            "master service agreement",
            "subscription agreement",
            "service level agreement",
            "saas",
            "software-as-a-service",
            "distributor agreement",
            "distribution agreement",
            "reseller agreement",
            "customer agreement",
            "order form",
            "professional services agreement",
            "promotion agreement",
            "commercial agreement",
        ),
        "type_weight": 1.15,
    },
    PEDocumentType.VENDOR_CONTRACT.value: {
        "label": "Vendor Contract",
        "patterns": (
            "supply agreement",
            "supplier agreement",
            "vendor agreement",
            "procurement",
            "subcontractor agreement",
            "outsourcing agreement",
            "manufacturing agreement",
            "vendor",
            "purchase order",
        ),
        "type_weight": 1.1,
    },
    PEDocumentType.NDA.value: {
        "label": "NDA",
        "patterns": (
            "non-disclosure agreement",
            "nda",
            "mutual non-disclosure",
            "disclosing party",
            "receiving party",
            "confidentiality agreement",
            "mutual confidentiality",
            "confidential information",
        ),
        "type_weight": 1.1,
    },
    PEDocumentType.TAX_DOCUMENT.value: {
        "label": "Tax Document",
        "patterns": (
            "tax sharing agreement",
            "tax allocation agreement",
            "tax receivable agreement",
            "section 382",
            "net operating loss",
            "nol",
            "transfer pricing",
        ),
        "type_weight": 1.0,
    },
    PEDocumentType.REGULATORY_FILING.value: {
        "label": "Regulatory Filing",
        "patterns": (
            "filed with the securities and exchange commission",
            "quarterly report pursuant to section 13",
            "annual report pursuant to section 13",
            "commission file number",
            "fda correspondence",
            "hsr filing",
            "regulatory filing",
        ),
        "type_weight": 1.0,
    },
    PEDocumentType.INSURANCE_DOCUMENT.value: {
        "label": "Insurance Document",
        "patterns": (
            "insurance policy",
            "certificate of insurance",
            "directors and officers liability",
            "d&o policy",
            "representation and warranty insurance",
        ),
        "type_weight": 1.0,
    },
    PEDocumentType.CHARTER_DOCUMENT.value: {
        "label": "Charter Document",
        "patterns": (
            "certificate of incorporation",
            "articles of incorporation",
            "bylaws",
            "amended and restated bylaws",
            "limited liability company agreement",
            "llc agreement",
        ),
        "type_weight": 1.0,
    },
    PEDocumentType.POLICY_DOCUMENT.value: {
        "label": "Policy Document",
        "patterns": (
            "policy",
            "code of conduct",
            "employee handbook",
            "information security policy",
            "privacy policy",
            "data retention policy",
        ),
        "type_weight": 0.95,
    },
    PEDocumentType.LEGAL_CONTRACT.value: {
        "label": "Legal Contract",
        "patterns": (
            "agreement",
            "this agreement",
            "service agreement",
            "consulting agreement",
            "term and termination",
            "termination",
            "governing law",
            "indemnification",
            "liability",
            "obligations",
            "contractor",
            "effective date",
            "renewal",
            "notice period",
        ),
        "type_weight": 0.35,
        "generic": True,
        "fallback_only": True,
    },
    PEDocumentType.OTHER.value: {
        "label": "Other",
        "patterns": (),
        "type_weight": 0.0,
        "generic": True,
    },
}


def is_known_doc_type(doc_type: str | None) -> bool:
    return bool(doc_type) and doc_type in ALL_DOC_TYPE_VALUE_SET


def is_generic_doc_type(doc_type: str | None) -> bool:
    return bool(doc_type) and doc_type in GENERIC_DOC_TYPES


def validate_doc_type(doc_type: str | None, *, context: str = "doc_type") -> str:
    if not is_known_doc_type(doc_type):
        raise ValueError(f"Unknown {context}: {doc_type}")
    return str(doc_type)


def validate_doc_type_list(doc_types: Iterable[str] | None, *, context: str) -> list[str]:
    if not doc_types:
        return []
    normalized: list[str] = []
    for index, doc_type in enumerate(doc_types):
        normalized.append(validate_doc_type(doc_type, context=f"{context}[{index}]"))
    return normalized
