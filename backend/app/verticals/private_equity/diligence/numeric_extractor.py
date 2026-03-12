"""LLM-backed structured financial numeric extraction for PE diligence (stage 5b).

Flow:
  1. Select chunks from financial_statement / qoe_report classified docs
     (falls back to all docs if none classified)
  2. Assemble candidate text up to pe_diligence_llm_numeric_max_chunks chunks
  3. Call LLM via StructuredLLMRunner → get ExtractedFinancials JSON
  4. Return dict stored in analysis_run.metadata_json["llm_financials"]

Key design:
  - Static, cache-eligible system prompt (shared across all runs)
  - Single LLM call per analysis run
  - Fails gracefully: returns None on any error, pipeline continues
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.core.rag.hybrid_retriever import HybridRetriever
from app.utils.logging import logger

# ─── Document types that carry financial data ───────────────────────────────

FINANCIAL_DOC_TYPES = {"financial_statement", "qoe_report", "cim"}

# ─── Hybrid search query for financial content ────────────────────────────────

_FINANCIAL_QUERY = (
    "revenue EBITDA net income operating income gross profit "
    "capital expenditure free cash flow financial results year 2022 2023 2024 "
    "balance sheet leverage ratio interest coverage"
)

# ─── Pydantic output models ─────────────────────────────────────────────────


class ExtractedFinancialYear(BaseModel):
    year: str
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    ebitda_margin: Optional[float] = None
    gross_profit: Optional[float] = None
    net_income: Optional[float] = None
    capex: Optional[float] = None
    free_cash_flow: Optional[float] = None


class ExtractedMetric(BaseModel):
    metric_name: str
    value: Optional[float] = None
    unit: Optional[str] = None        # "USD", "%", "x"
    period: Optional[str] = None      # "2023", "LTM", "Q3 2024"
    definition: Optional[str] = None  # "adjusted", "reported", "pro-forma"
    raw_quote: Optional[str] = None
    confidence: Optional[float] = None


class ExtractedFinancials(BaseModel):
    currency: str = "USD"
    historical: List[ExtractedFinancialYear] = Field(default_factory=list)
    ratios: List[ExtractedMetric] = Field(default_factory=list)
    other_metrics: List[ExtractedMetric] = Field(default_factory=list)
    data_quality_notes: Optional[str] = None


# ─── System prompt (static, cache-eligible) ─────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a financial analyst extracting structured financial data from PE diligence documents.\n\n"
    "Rules:\n"
    "1. Extract only values explicitly stated in the text — never infer or project.\n"
    "2. Preserve exact precision (e.g., $12.3M not $12M unless the source says $12M).\n"
    "3. All dollar amounts in USD unless clearly stated otherwise; record currency in the output.\n"
    "4. Use millions as the base unit for historical P&L figures (revenue, EBITDA, etc.).\n"
    "5. Record the fiscal year or period label exactly as it appears in the document.\n"
    "6. If the same metric appears with different definitions (GAAP vs. adjusted), extract both and note definition.\n"
    "7. For ratios (leverage, coverage), record the numeric value and unit (e.g., '3.5x', '2.1x').\n"
    "8. If data quality is poor (missing periods, conflicting figures), note it in data_quality_notes.\n\n"
    "Return a single JSON object matching this structure:\n"
    "{\n"
    "  \"currency\": \"USD\",\n"
    "  \"historical\": [\n"
    "    {\n"
    "      \"year\": \"2023\",\n"
    "      \"revenue\": 45.2,\n"
    "      \"ebitda\": 8.1,\n"
    "      \"ebitda_margin\": 17.9,\n"
    "      \"gross_profit\": 18.5,\n"
    "      \"net_income\": 4.3,\n"
    "      \"capex\": 1.2,\n"
    "      \"free_cash_flow\": 6.9\n"
    "    }\n"
    "  ],\n"
    "  \"ratios\": [\n"
    "    {\"metric_name\": \"leverage_ratio\", \"value\": 3.5, \"unit\": \"x\", \"period\": \"LTM\", \"definition\": \"net debt / EBITDA\", \"raw_quote\": \"...\", \"confidence\": 0.88}\n"
    "  ],\n"
    "  \"other_metrics\": [\n"
    "    {\"metric_name\": \"arr\", \"value\": 12.0, \"unit\": \"USD\", \"period\": \"2023\", \"definition\": \"annual recurring revenue\", \"raw_quote\": \"...\", \"confidence\": 0.85}\n"
    "  ],\n"
    "  \"data_quality_notes\": null\n"
    "}\n\n"
    "Only include years/metrics you actually found. Null out any fields not present."
)

# ─── Main extractor class ────────────────────────────────────────────────────


class LLMNumericExtractor:
    """Extracts structured financial metrics from document chunks via LLM."""

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
        self.max_chunks = settings.pe_diligence_llm_numeric_max_chunks
        self.min_confidence = settings.pe_diligence_llm_numeric_min_confidence

    def _build_candidate_text(self, chunks: List[dict]) -> str:
        parts = []
        for i, row in enumerate(chunks, 1):
            doc_id = row.get("document_id", "")[:8]
            page = row.get("page_number") or "?"
            text = (row.get("text") or "").strip()
            if text:
                parts.append(f"[Excerpt {i}] (doc:{doc_id}... page:{page})\n{text}")
        return "\n\n---\n\n".join(parts)

    async def extract(
        self,
        db: Session,
        document_ids: List[str],
        document_classifications: Dict[str, dict],
        room_id: str,
        run_id: str,
    ) -> Optional[dict]:
        """Run LLM financial extraction using hybrid retrieval. Returns dict or None on failure."""
        # Scope to financial doc types if classified, else use all room documents
        financial_doc_ids = [
            doc_id for doc_id, cls in document_classifications.items()
            if cls.get("document_type") in FINANCIAL_DOC_TYPES
        ] or document_ids

        # Use hybrid retrieval to find financially relevant chunks
        try:
            retriever = HybridRetriever(db)
            raw_chunks = retriever.retrieve(
                query=_FINANCIAL_QUERY,
                document_ids=financial_doc_ids,
                top_k=self.max_chunks,
            )
        except Exception as exc:
            logger.warning(
                "HybridRetriever failed for financial extraction; falling back",
                extra={"room_id": room_id, "run_id": run_id, "error": str(exc)[:200]},
            )
            raw_chunks = []

        if not raw_chunks:
            logger.info(
                "LLM numeric extraction: no chunks retrieved",
                extra={"room_id": room_id, "run_id": run_id},
            )
            return None

        # Map hybrid retriever output to expected format
        chunks = [
            {
                "document_id": r.get("document_id"),
                "page_number": r.get("page_number"),
                "section_type": r.get("section_type"),
                "text": r.get("text", ""),
            }
            for r in raw_chunks
        ]

        candidate_text = self._build_candidate_text(chunks)
        if not candidate_text.strip():
            return None

        user_content = (
            "Extract structured financial data from the following document excerpts:\n\n"
            + candidate_text
        )

        try:
            result = await self.runner.run_structured(
                user_content=user_content,
                system_prompt=_SYSTEM_PROMPT,
                pydantic_model=ExtractedFinancials,
                use_cache=True,
            )
        except Exception as exc:
            logger.warning(
                "LLM numeric extraction runner failed",
                extra={"room_id": room_id, "run_id": run_id, "error": str(exc)[:300]},
            )
            return None

        data = result.get("data")
        if not data or not isinstance(data, dict):
            return None

        # Filter low-confidence other_metrics and ratios
        def _filter_metrics(metrics: List[Any]) -> List[Any]:
            out = []
            for m in metrics:
                if isinstance(m, dict):
                    conf = m.get("confidence")
                    if conf is None or float(conf) >= self.min_confidence:
                        out.append(m)
            return out

        data["ratios"] = _filter_metrics(data.get("ratios") or [])
        data["other_metrics"] = _filter_metrics(data.get("other_metrics") or [])

        # Only return if we extracted at least one year or one metric
        has_data = bool(data.get("historical") or data.get("ratios") or data.get("other_metrics"))
        if not has_data:
            return None

        logger.info(
            "LLM numeric extraction succeeded",
            extra={
                "room_id": room_id,
                "run_id": run_id,
                "chunks_sent": len(chunks),
                "table_chunks": sum(1 for r in chunks if r.get("section_type") in {"table", "key_value_pairs"}),
                "financial_doc_scoped": len(financial_doc_ids) < len(document_ids),
                "years": len(data.get("historical") or []),
                "ratios": len(data.get("ratios") or []),
                "other_metrics": len(data.get("other_metrics") or []),
            },
        )
        return data
