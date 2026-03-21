from __future__ import annotations

import json
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.utils.logging import logger
from app.verticals.private_equity.diligence.doc_types import ALL_DOC_TYPE_VALUES, PEDocumentType

ALLOWED_DOC_TYPES = list(ALL_DOC_TYPE_VALUES)


class DocumentClassificationCandidate(BaseModel):
    document_id: str
    rule_anchor_id: str
    document_type: PEDocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: Optional[str] = None
    signals: List[str] = Field(default_factory=list)


class DocumentClassificationBatch(BaseModel):
    classifications: List[DocumentClassificationCandidate] = Field(default_factory=list)


class PEDiligenceClassificationAdapter:
    def __init__(self, runner: StructuredLLMRunner | None = None):
        if runner is None:
            llm_client = LLMClient(
                api_key=settings.anthropic_api_key,
                model=settings.synthesis_llm_model,
                max_tokens=settings.synthesis_llm_max_tokens,
                max_input_chars=settings.llm_max_input_chars,
                timeout_seconds=settings.synthesis_llm_timeout_seconds,
            )
            runner = StructuredLLMRunner(llm_client)
        self.runner = runner

    async def classify_low_confidence(self, doc_inputs: List[dict]) -> Dict[str, dict]:
        if not doc_inputs:
            return {}

        system_prompt = (
            "You classify PE diligence documents into a fixed taxonomy. "
            "Return only the schema fields. "
            "Each classification must include the exact rule_anchor_id provided in input for that document. "
            "Use conservative confidence: if uncertain, set document_type='other' and confidence <= 0.5. "
            "Allowed document_type values: "
            + ", ".join(ALLOWED_DOC_TYPES)
            + ". "
            "Classify to the MOST SPECIFIC type available. "
            "Use 'legal_contract' only as a generic fallback when the document is clearly a contract "
            "but does not fit a more specific type like customer_contract, vendor_contract, ip_license, "
            "employment_agreement, nda, purchase_agreement, merger_agreement, shareholder_agreement, or disclosure_schedule. "
            "Use 'amendment' for any document that modifies, supplements, or restates an existing agreement, "
            "including amendments, addenda, side letters, joinders, or amended-and-restated contracts. "
            "If a document is titled 'Amended and Restated [Agreement Name]', classify it as 'amendment' with "
            "high confidence. "
            "Use 'disclosure_schedule' for disclosure letters, schedules of exceptions, or seller/company disclosure schedules. "
            "Use 'regulatory_filing' only for the filing itself, not an exhibit contract attached to a filing. "
            "Use 'offering_memorandum' for CIM/offering memo style sale materials. "
            "Use 'purchase_agreement' for SPA/stock purchase/asset purchase agreements and "
            "'merger_agreement' for agreement-and-plan-of-merger style transaction documents."
        )
        user_content = json.dumps({"documents": doc_inputs}, ensure_ascii=False)

        result = await self.runner.run_structured(
            user_content=user_content,
            system_prompt=system_prompt,
            pydantic_model=DocumentClassificationBatch,
            use_cache=False,
        )

        items = result.get("data", {}).get("classifications", [])
        out: Dict[str, dict] = {}
        for row in items:
            doc_id = row.get("document_id")
            rule_anchor_id = row.get("rule_anchor_id")
            doc_type = row.get("document_type")
            confidence = row.get("confidence")
            if isinstance(doc_type, PEDocumentType):
                doc_type = doc_type.value
            if not doc_id or not rule_anchor_id or doc_type not in ALLOWED_DOC_TYPES:
                continue
            if confidence is None:
                confidence = 0.0
            out[doc_id] = {
                "rule_anchor_id": str(rule_anchor_id),
                "document_type": doc_type,
                "confidence": round(float(confidence), 3),
                "needs_review": float(confidence) < 0.72,
                "signals": (row.get("signals") or [])[:6],
                "rationale": row.get("rationale"),
            }

        logger.info(
            "PE diligence LLM classification fallback completed",
            extra={
                "input_docs": len(doc_inputs),
                "classified_docs": len(out),
            },
        )
        return out
