"""LLM-backed cross-document findings synthesis for PE diligence (stage 7).

Replaces the 1-hit-per-finding rule-based approach with a senior PE analyst
reasoning over all signals to produce ≤15 cross-document synthesized findings.

Falls back gracefully to rule-based findings on any LLM error.

Input signals assembled into user content:
  - Clause hits (regex) with quantified fields from structured clauses
  - Missing clause flags from classified documents
  - Numeric reconciliation signals
  - LLM financial data (if available)
  - Checklist gaps (missing/partial items)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.utils.logging import logger

# ─── Pydantic output models ─────────────────────────────────────────────────


class SynthesizedFinding(BaseModel):
    category: str          # contract, debt, commercial, ip, people, spa, missing_clause, numeric_reconciliation
    severity: str          # high, medium, low
    title: str
    description: str       # cross-document reasoning, quantified where possible
    recommendation: str
    supporting_evidence: List[str] = Field(default_factory=list)  # clause types or metric names
    confidence: Optional[float] = None


class SynthesizedFindings(BaseModel):
    findings: List[SynthesizedFinding] = Field(default_factory=list)
    synthesis_notes: Optional[str] = None


# ─── System prompt (static, cache-eligible) ─────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a senior PE diligence analyst synthesizing findings across multiple signals "
    "from a deal room. Your job is to produce a concise, high-quality set of ≤15 findings "
    "that a deal team would act on before Investment Committee.\n\n"
    "Guidelines:\n"
    "1. Merge related signals into single findings (e.g., change-of-control + assignment consent "
    "in the same contract family → one finding about consent risk).\n"
    "2. Quantify wherever possible using the structured fields provided (cap amounts, survival "
    "periods, thresholds, notice days, etc.).\n"
    "3. Cross-reference interacting risks: e.g., high leverage + tight interest coverage covenant "
    "= compounding downside risk → elevate severity.\n"
    "4. Flag missing clauses as genuine diligence gaps, not just process items.\n"
    "5. Rank by severity: high → medium → low. Never fabricate data.\n"
    "6. Write descriptions in plain English with specific numbers where available.\n"
    "7. Recommendations must be actionable (e.g., 'request redline', 'model covenant headroom', "
    "'add to closing condition list').\n\n"
    "Return JSON:\n"
    "{\n"
    "  \"findings\": [\n"
    "    {\n"
    "      \"category\": \"contract\",\n"
    "      \"severity\": \"high\",\n"
    "      \"title\": \"...\",\n"
    "      \"description\": \"...\",\n"
    "      \"recommendation\": \"...\",\n"
    "      \"supporting_evidence\": [\"change_of_control\", \"assignment_consent\"],\n"
    "      \"confidence\": 0.87\n"
    "    }\n"
    "  ],\n"
    "  \"synthesis_notes\": \"...\" or null\n"
    "}"
)

# ─── Input assembly helpers ──────────────────────────────────────────────────

_MAX_INPUT_CHARS = 30_000


def _fmt_clause_hits(
    clause_hits: List[dict],
    structured_clauses_by_type: Dict[str, List[dict]],
    max_hits: int = 40,
) -> str:
    if not clause_hits:
        return ""
    lines = ["## Clause Signals"]
    seen: set = set()
    for hit in clause_hits[:max_hits]:
        ct = hit["clause_type"]
        if ct in seen:
            continue
        seen.add(ct)
        ev = hit.get("evidence", {})
        quote = (ev.get("quote") or "")[:200]
        line = f"- [{ct}] quote: \"{quote}\""
        # Append quantified fields from structured clause
        sc = (structured_clauses_by_type.get(ct) or [None])[0]
        if sc:
            fields = sc.get("extracted_fields") or {}
            details = []
            if fields.get("cap_amount"):
                details.append(f"cap=${fields['cap_amount']:,.0f}")
            if fields.get("survival_months"):
                details.append(f"survival={fields['survival_months']}mo")
            if fields.get("basket_amount"):
                details.append(f"basket=${fields['basket_amount']:,.0f}")
            if fields.get("threshold_value") is not None and fields.get("threshold_unit"):
                details.append(f"threshold={fields['threshold_value']}{fields['threshold_unit']}")
            if fields.get("termination_notice_days"):
                details.append(f"notice={fields['termination_notice_days']}d")
            if fields.get("consent_required") and fields.get("consent_parties"):
                details.append(f"consent_parties={','.join(fields['consent_parties'][:2])}")
            if fields.get("earnout_metric"):
                details.append(f"earnout={fields.get('earnout_period_months','?')}mo on {fields['earnout_metric']}")
            if fields.get("mac_carveouts"):
                details.append(f"mac_carveouts={','.join(fields['mac_carveouts'][:2])}")
            if sc.get("interpretation"):
                details.append(f"interpretation: {sc['interpretation'][:120]}")
            if details:
                line += " | " + " · ".join(details)
        lines.append(line)
    return "\n".join(lines)


def _fmt_numeric(numeric_signals: Dict[str, List[dict]]) -> str:
    if not numeric_signals:
        return ""
    lines = ["## Numeric Signals"]
    for metric, vals in numeric_signals.items():
        amounts = [f"${v['value']:,.0f}" for v in vals[:4]]
        lines.append(f"- {metric}: {', '.join(amounts)} across {len(vals)} source(s)")
    return "\n".join(lines)


def _fmt_llm_financials(llm_financials: Optional[dict]) -> str:
    if not llm_financials:
        return ""
    lines = ["## LLM-Extracted Financials"]
    currency = llm_financials.get("currency", "USD")
    for yr in (llm_financials.get("historical") or []):
        year = yr.get("year", "?")
        rev = yr.get("revenue")
        ebitda = yr.get("ebitda")
        margin = yr.get("ebitda_margin")
        parts = []
        if rev is not None:
            parts.append(f"Revenue={rev:.1f}M {currency}")
        if ebitda is not None:
            parts.append(f"EBITDA={ebitda:.1f}M")
        if margin is not None:
            parts.append(f"Margin={margin:.1f}%")
        if parts:
            lines.append(f"- {year}: {', '.join(parts)}")
    for ratio in (llm_financials.get("ratios") or []):
        val = ratio.get("value")
        if val is not None:
            lines.append(f"- {ratio['metric_name']}: {val}{ratio.get('unit','')}"
                         + (f" ({ratio['definition']})" if ratio.get("definition") else ""))
    notes = llm_financials.get("data_quality_notes")
    if notes:
        lines.append(f"- Data quality note: {notes}")
    return "\n".join(lines)


def _fmt_checklist(checklist_entries: List[dict]) -> str:
    gaps = [e["item"] for e in checklist_entries if e["item"].get("status") in {"missing", "partial"}]
    if not gaps:
        return ""
    lines = ["## Checklist Gaps"]
    for item in gaps:
        lines.append(f"- [{item['status'].upper()}] {item['title']} (priority={item['priority']})")
    return "\n".join(lines)


def _fmt_classifications(document_classifications: Dict[str, dict]) -> str:
    if not document_classifications:
        return ""
    counts: Dict[str, int] = {}
    for cls in document_classifications.values():
        dt = cls.get("document_type") or "other"
        counts[dt] = counts.get(dt, 0) + 1
    lines = ["## Document Types in Room"]
    for dt, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {dt}: {cnt} doc(s)")
    return "\n".join(lines)


def _assemble_user_content(
    clause_hits: List[dict],
    structured_clauses_by_type: Dict[str, List[dict]],
    numeric_signals: Dict[str, List[dict]],
    llm_financials: Optional[dict],
    checklist_entries: List[dict],
    document_classifications: Dict[str, dict],
) -> str:
    sections = [
        _fmt_classifications(document_classifications),
        _fmt_clause_hits(clause_hits, structured_clauses_by_type),
        _fmt_numeric(numeric_signals),
        _fmt_llm_financials(llm_financials),
        _fmt_checklist(checklist_entries),
    ]
    content = "\n\n".join(s for s in sections if s)
    if len(content) > _MAX_INPUT_CHARS:
        content = content[:_MAX_INPUT_CHARS] + "\n\n[truncated]"
    return "Synthesize findings from the following diligence signals:\n\n" + content


# ─── Main synthesizer class ──────────────────────────────────────────────────


class LLMFindingsSynthesizer:
    """Cross-document findings synthesizer using LLM reasoning."""

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

    async def synthesize(
        self,
        *,
        clause_hits: List[dict],
        structured_clauses_by_type: Dict[str, List[dict]],
        numeric_signals: Dict[str, List[dict]],
        llm_financials: Optional[dict],
        checklist_entries: List[dict],
        document_classifications: Dict[str, dict],
        room_id: str,
        run_id: str,
    ) -> Optional[List[dict]]:
        """Synthesize findings. Returns list of finding dicts or None on failure."""
        user_content = _assemble_user_content(
            clause_hits=clause_hits,
            structured_clauses_by_type=structured_clauses_by_type,
            numeric_signals=numeric_signals,
            llm_financials=llm_financials,
            checklist_entries=checklist_entries,
            document_classifications=document_classifications,
        )

        try:
            result = await self.runner.run_structured(
                user_content=user_content,
                system_prompt=_SYSTEM_PROMPT,
                pydantic_model=SynthesizedFindings,
                use_cache=False,
            )
        except Exception as exc:
            logger.warning(
                "LLM findings synthesizer runner failed",
                extra={"room_id": room_id, "run_id": run_id, "error": str(exc)[:300]},
            )
            return None

        data = result.get("data") or {}
        raw_findings = data.get("findings") or []
        if not raw_findings:
            return None

        # Convert to pipeline finding dicts (same shape as _build_findings output)
        out: List[dict] = []
        for raw in raw_findings:
            if not isinstance(raw, dict):
                continue
            # Try to find a primary source from clause hits matching supporting evidence
            primary_ev: Optional[dict] = None
            for evidence_key in (raw.get("supporting_evidence") or []):
                for hit in clause_hits:
                    if hit.get("clause_type") == evidence_key:
                        primary_ev = hit.get("evidence")
                        break
                if primary_ev:
                    break

            out.append(
                {
                    "category": raw.get("category", "contract"),
                    "severity": raw.get("severity", "medium"),
                    "title": raw.get("title", "")[:200],
                    "description": raw.get("description", "")[:1000],
                    "recommendation": raw.get("recommendation", "")[:500],
                    "status": "open",
                    "source_document_id": primary_ev.get("source_document_id") if primary_ev else None,
                    "source_chunk_id": primary_ev.get("source_chunk_id") if primary_ev else None,
                    "source_page_number": primary_ev.get("source_page_number") if primary_ev else None,
                    "evidence_quote": (primary_ev.get("quote") if primary_ev else None),
                    "confidence": raw.get("confidence"),
                    "metadata_json": {
                        "engine": "llm_synthesis_v1",
                        "supporting_evidence": raw.get("supporting_evidence") or [],
                        "synthesis_notes": data.get("synthesis_notes"),
                    },
                    "evidence_list": [primary_ev] if primary_ev else [],
                }
            )

        return out[:15]  # cap at 15 per plan
