from __future__ import annotations

import json
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.utils.logging import logger


ALLOWED_DOC_TYPES = [
    "amendment",
    "offering_memorandum",
    "purchase_agreement",
    "financial_statement",
    "qoe_report",
    "legal_contract",
    "other",
]


class DocumentClassificationCandidate(BaseModel):
    document_id: str
    rule_anchor_id: str
    document_type: Literal[
        "amendment",
        "offering_memorandum",
        "purchase_agreement",
        "financial_statement",
        "qoe_report",
        "legal_contract",
        "other",
    ]
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
            "Use conservative confidence: if uncertain, set document_type='other' and confidence <= 0.6. "
            "Allowed document_type values: "
            + ", ".join(ALLOWED_DOC_TYPES)
            + ". "
            "Use 'amendment' for any document that modifies, supplements, or restates an existing agreement, "
            "including amendments, addenda, side letters, joinders, or amended-and-restated contracts. "
            "If a document is titled 'Amended and Restated [Agreement Name]', classify it as 'amendment' with "
            "high confidence — it supersedes the original rather than merely modifying it."
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
