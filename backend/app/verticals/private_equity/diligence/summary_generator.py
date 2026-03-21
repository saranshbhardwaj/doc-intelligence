"""LLM-backed diligence summary generation for PE diligence (stage 9).

Replaces the static markdown template with a real LLM-generated narrative
that includes deal-specific priority risks and tailored management questions.

Falls back gracefully to the template summary on any LLM error.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.utils.logging import logger
from app.verticals.private_equity.diligence.formatting import fmt_checklist_summary, fmt_classifications
from app.verticals.private_equity.diligence.normalization import (
    normalize_management_questions,
    normalize_priority_risks,
    normalize_summary_payload,
    normalize_text_note,
)

# ─── Pydantic output models ─────────────────────────────────────────────────


class PriorityRisk(BaseModel):
    title: str
    reasoning: str   # WHY this is priority, with specific numbers/parties
    severity: str    # high, medium, low


class ManagementQuestion(BaseModel):
    question: str
    rationale: str              # WHY ask — tied to specific findings
    related_finding: Optional[str] = None


class DiligenceSummary(BaseModel):
    executive_narrative: str                            # 200-400 words
    priority_risks: List[PriorityRisk] = Field(default_factory=list)        # ≤5
    management_questions: List[ManagementQuestion] = Field(default_factory=list)  # ≤7
    confidence: Optional[float] = None
    data_quality_assessment: Optional[str] = None


# ─── System prompt (static, cache-eligible) ─────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a senior PE analyst writing the executive diligence summary for an Investment Committee. "
    "Your summary will be read by busy partners who need to quickly assess risk and decide on next steps.\n\n"
    "Requirements:\n"
    "1. Executive narrative: 200-400 words. Concise, deal-specific. State what was found, not just "
    "what was looked for. Reference actual clause types, dollar amounts, counterparties, and metrics "
    "extracted from the documents.\n"
    "2. Priority risks: ≤5 items. Each must include specific reasoning (not generic). Include dollar "
    "amounts, thresholds, party names, or time periods where available.\n"
    "3. Management questions: ≤7 items. Tailored to the actual findings — not generic diligence "
    "questions. Each must explain WHY it is being asked, tied to a specific finding.\n"
    "4. Data quality assessment: brief note if financial data quality is poor, missing periods, "
    "or numeric reconciliation issues were found.\n"
    "5. Never fabricate data. If a finding has no supporting evidence, do not include it.\n\n"
    "Return JSON:\n"
    "{\n"
    "  \"executive_narrative\": \"...\",\n"
    "  \"priority_risks\": [\n"
    "    {\"title\": \"...\", \"reasoning\": \"...\", \"severity\": \"high\"}\n"
    "  ],\n"
    "  \"management_questions\": [\n"
    "    {\"question\": \"...\", \"rationale\": \"...\", \"related_finding\": \"change_of_control\"}\n"
    "  ],\n"
    "  \"confidence\": 0.82,\n"
    "  \"data_quality_assessment\": null\n"
    "}"
)

_MAX_INPUT_CHARS = 40_000

# ─── Input assembly ──────────────────────────────────────────────────────────


def _fmt_findings(finding_entries: List[dict]) -> str:
    if not finding_entries:
        return ""
    lines = ["## Key Findings (post-verification)"]
    for f in finding_entries[:20]:
        sev = f.get("severity", "medium").upper()
        title = f.get("title", "")
        desc = f.get("description", "")[:300]
        lines.append(f"- [{sev}] {title}: {desc}")
    return "\n".join(lines)


def _fmt_financials(llm_financials: Optional[dict]) -> str:
    if not llm_financials:
        return ""
    lines = ["## Financial Summary"]
    currency = llm_financials.get("currency", "USD")
    for yr in (llm_financials.get("historical") or []):
        year = yr.get("year", "?")
        parts = []
        if yr.get("revenue") is not None:
            parts.append(f"Rev={yr['revenue']:.1f}M {currency}")
        if yr.get("ebitda") is not None:
            parts.append(f"EBITDA={yr['ebitda']:.1f}M")
        if yr.get("ebitda_margin") is not None:
            parts.append(f"Margin={yr['ebitda_margin']:.1f}%")
        if parts:
            lines.append(f"- {year}: {', '.join(parts)}")
    notes = llm_financials.get("data_quality_notes")
    if notes:
        lines.append(f"- Data quality: {notes}")
    return "\n".join(lines)


def _fmt_verification(verification_stats: Dict[str, int]) -> str:
    verified = verification_stats.get("verified", 0)
    needs_review = verification_stats.get("needs_review", 0)
    total = verification_stats.get("total", 0)
    return f"## Verification: {verified}/{total} verified, {needs_review} needs review"


# ─── Main generator class ────────────────────────────────────────────────────


class LLMSummaryGenerator:
    """Generates LLM-powered diligence executive summary."""

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

    async def generate(
        self,
        *,
        room_name: str,
        finding_entries: List[dict],
        checklist_entries: List[dict],
        document_classifications: Dict[str, dict],
        verification_stats: Dict[str, int],
        llm_financials: Optional[dict],
        structured_clauses_by_type: Dict[str, List[dict]],
        room_id: str,
        run_id: str,
    ) -> Optional[dict]:
        """Generate summary. Returns summary dict (same shape as _build_summary) or None."""
        sections = [
            f"# Diligence Summary — {room_name}",
            fmt_classifications(document_classifications, multiline=False),
            _fmt_verification(verification_stats),
            _fmt_financials(llm_financials),
            fmt_checklist_summary(checklist_entries, detailed=False),
            _fmt_findings(finding_entries),
        ]
        content = "\n\n".join(s for s in sections if s)
        if len(content) > _MAX_INPUT_CHARS:
            content = content[:_MAX_INPUT_CHARS] + "\n\n[truncated]"

        user_content = f"Generate the diligence executive summary for:\n\n{content}"

        try:
            result = await self.runner.run_structured(
                user_content=user_content,
                system_prompt=_SYSTEM_PROMPT,
                pydantic_model=DiligenceSummary,
                use_cache=True,
            )
        except Exception as exc:
            logger.warning(
                "LLM summary generator runner failed",
                extra={"room_id": room_id, "run_id": run_id, "error": str(exc)[:300]},
            )
            return None

        data = result.get("data") or {}
        narrative = (data.get("executive_narrative") or "").strip()
        if not narrative:
            return None

        priority_risks = normalize_priority_risks(data.get("priority_risks"))
        management_questions = normalize_management_questions(data.get("management_questions"))
        data_quality_assessment = normalize_text_note(data.get("data_quality_assessment"), max_length=500)

        # Build markdown output (mirrors _build_summary structure)
        md_lines = [
            f"# Diligence Overview — {room_name}",
            "",
            narrative,
            "",
            "## Priority Risks",
        ]
        for i, risk in enumerate(priority_risks[:5], 1):
            sev_label = risk.get("severity", "medium").capitalize()
            md_lines.append(
                f"{i}. **[{sev_label}] {risk.get('title', '')}** — {risk.get('reasoning', '')}"
            )
        md_lines += ["", "## Management Questions to Ask"]
        for i, q in enumerate(management_questions[:7], 1):
            rationale = q.get("rationale", "")
            md_lines.append(
                f"{i}. {q.get('question', '')}"
                + (f" *(Rationale: {rationale})*" if rationale else "")
            )
        if data_quality_assessment:
            md_lines += ["", f"**Data Quality Note:** {data_quality_assessment}"]

        markdown = "\n".join(md_lines)

        # Build citations from top findings
        citations = []
        for finding in finding_entries[:5]:
            ev = (finding.get("evidence_list") or [None])[0]
            citations.append(
                {
                    "entity": finding["title"],
                    "document_id": ev.get("source_document_id") if ev else None,
                    "page_number": ev.get("source_page_number") if ev else None,
                    "quote": ((ev.get("quote") if ev else finding.get("evidence_quote")) or "")[:220],
                    "confidence": ev.get("confidence") if ev else finding.get("confidence"),
                }
            )

        evidence_list = [f["evidence_list"][0] for f in finding_entries if f.get("evidence_list")][:5]

        logger.info(
            "LLM summary generation succeeded",
            extra={
                "room_id": room_id,
                "run_id": run_id,
                "priority_risks": len(priority_risks),
                "management_questions": len(management_questions),
            },
        )

        return normalize_summary_payload({
            "markdown": markdown,
            "citations": citations,
            "confidence": data.get("confidence") or 0.80,
            "evidence_list": evidence_list,
            "metadata": {
                "priority_risks": [
                    {"title": risk.get("title"), "severity": risk.get("severity"), "summary": risk.get("reasoning")}
                    for risk in priority_risks
                ],
                "management_questions": management_questions,
                "data_quality_assessment": data_quality_assessment,
                "document_classification": document_classifications,
                "verification": verification_stats,
            },
        })
