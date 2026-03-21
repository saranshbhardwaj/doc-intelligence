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

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.verticals.private_equity.diligence.formatting import fmt_checklist_summary, fmt_classifications

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.utils.logging import logger
from app.verticals.private_equity.diligence.normalization import normalize_findings

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




def _assemble_user_content(
    clause_hits: List[dict],
    structured_clauses_by_type: Dict[str, List[dict]],
    numeric_signals: Dict[str, List[dict]],
    llm_financials: Optional[dict],
    checklist_entries: List[dict],
    document_classifications: Dict[str, dict],
) -> str:
    sections = [
        fmt_classifications(document_classifications, multiline=True),
        _fmt_clause_hits(clause_hits, structured_clauses_by_type),
        _fmt_numeric(numeric_signals),
        _fmt_llm_financials(llm_financials),
        fmt_checklist_summary(checklist_entries, detailed=True),
    ]
    content = "\n\n".join(s for s in sections if s)
    if len(content) > _MAX_INPUT_CHARS:
        content = content[:_MAX_INPUT_CHARS] + "\n\n[truncated]"
    return "Synthesize findings from the following diligence signals:\n\n" + content


def _fmt_per_doc_findings(per_doc_findings: List[dict], max_findings: int = 60) -> str:
    """Format per-doc findings for V2 synthesis prompt, grouped by document."""
    if not per_doc_findings:
        return ""
    # Group by source_document_id
    by_doc: Dict[str, List[dict]] = {}
    for f in per_doc_findings[:max_findings]:
        doc_id = f.get("source_document_id") or "unknown"
        by_doc.setdefault(doc_id, []).append(f)
    lines = ["## Per-Document Findings"]
    for doc_id, findings in by_doc.items():
        filename = (findings[0].get("metadata_json") or {}).get("filename", doc_id[:12])
        doc_type = (findings[0].get("metadata_json") or {}).get("doc_type", "")
        lines.append(f"\n### {filename} ({doc_type})")
        for f in findings:
            sev = f.get("severity", "medium").upper()
            title = f.get("title", "")
            desc = (f.get("description") or "")[:200]
            meta = f.get("metadata_json") or {}
            assessment = meta.get("assessment")
            clause_type = meta.get("clause_type") or meta.get("playbook_slug")
            page = f.get("source_page_number")
            qualifiers = [part for part in [assessment, clause_type, f"page {page}" if page else None] if part]
            qualifier_text = f" ({', '.join(qualifiers)})" if qualifiers else ""
            lines.append(f"- [{sev}] {title}{qualifier_text}: {desc}")
    return "\n".join(lines)


def _candidate_evidence_from_findings(per_doc_findings: List[dict], supporting_evidence: List[str], category: Optional[str]) -> List[dict]:
    tokens = {str(item).strip().lower() for item in supporting_evidence if str(item).strip()}
    scored: List[tuple[int, float, dict]] = []
    for finding in per_doc_findings:
        metadata = finding.get("metadata_json") or {}
        candidates = {
            str(metadata.get("clause_type") or "").lower(),
            str(metadata.get("playbook_slug") or "").lower(),
            str(metadata.get("assessment") or "").lower(),
            str(finding.get("category") or "").lower(),
        }
        title_words = {word for word in str(finding.get("title") or "").lower().replace("-", " ").split() if len(word) > 3}
        score = len(tokens & candidates) + len(tokens & title_words)
        if category and str(finding.get("category") or "").lower() == str(category).lower():
            score += 1
        if score <= 0 and tokens:
            continue
        for ev in finding.get("evidence_list") or []:
            if isinstance(ev, dict) and ev.get("quote"):
                scored.append((score, float(finding.get("confidence") or 0.0), ev))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    out: List[dict] = []
    seen = set()
    for _, __, ev in scored:
        key = (ev.get("source_document_id"), ev.get("source_page_number"), ev.get("quote"))
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
        if len(out) >= 3:
            break
    return out


def _assemble_user_content_v2(
    per_doc_findings: List[dict],
    numeric_signals: Dict[str, List[dict]],
    llm_financials: Optional[dict],
    document_classifications: Dict[str, dict],
) -> str:
    sections = [
        fmt_classifications(document_classifications),
        _fmt_per_doc_findings(per_doc_findings),
        _fmt_numeric(numeric_signals),
        _fmt_llm_financials(llm_financials),
    ]
    content = "\n\n".join(s for s in sections if s)
    if len(content) > _MAX_INPUT_CHARS:
        content = content[:_MAX_INPUT_CHARS] + "\n\n[truncated]"
    return "Synthesize cross-document findings from the following per-document analysis:\n\n" + content


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
                use_cache=True,
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
            matched_evidence: List[dict] = []
            for evidence_key in (raw.get("supporting_evidence") or []):
                for hit in clause_hits:
                    if hit.get("clause_type") == evidence_key:
                        evidence = hit.get("evidence")
                        if isinstance(evidence, dict) and evidence.get("quote"):
                            matched_evidence.append(evidence)
                if len(matched_evidence) >= 3:
                    break
            primary_ev = matched_evidence[0] if matched_evidence else None

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
                    "evidence_list": matched_evidence,
                }
            )

        return normalize_findings(out, source_kind="cross_document_synthesis", limit=15)

    async def synthesize_v2(
        self,
        *,
        per_doc_findings: List[dict],
        numeric_signals: Dict[str, List[dict]],
        llm_financials: Optional[dict],
        document_classifications: Dict[str, dict],
        room_id: str,
        run_id: str,
    ) -> Optional[List[dict]]:
        """V2 synthesis: cross-document reasoning from per-doc findings (not clause_hits).

        Receives the full per-doc findings as input and produces ≤15 room-level synthesis
        findings that cross-reference patterns across documents.
        """
        user_content = _assemble_user_content_v2(
            per_doc_findings=per_doc_findings,
            numeric_signals=numeric_signals,
            llm_financials=llm_financials,
            document_classifications=document_classifications,
        )

        try:
            result = await self.runner.run_structured(
                user_content=user_content,
                system_prompt=_SYSTEM_PROMPT,
                pydantic_model=SynthesizedFindings,
                use_cache=True,
            )
        except Exception as exc:
            logger.warning(
                "V2 LLM findings synthesizer failed",
                extra={"room_id": room_id, "run_id": run_id, "error": str(exc)[:300]},
            )
            return None

        data = result.get("data") or {}
        raw_findings = data.get("findings") or []
        if not raw_findings:
            return None

        out: List[dict] = []
        for raw in raw_findings:
            if not isinstance(raw, dict):
                continue
            matched_evidence = _candidate_evidence_from_findings(
                per_doc_findings,
                raw.get("supporting_evidence") or [],
                raw.get("category"),
            )
            primary_ev = matched_evidence[0] if matched_evidence else None
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
                    "evidence_quote": primary_ev.get("quote") if primary_ev else None,
                    "confidence": raw.get("confidence"),
                    "metadata_json": {
                        "engine": "llm_synthesis_v2",
                        "supporting_evidence": raw.get("supporting_evidence") or [],
                        "synthesis_notes": data.get("synthesis_notes"),
                    },
                    "evidence_list": matched_evidence,
                }
            )

        logger.info(
            "V2 cross-doc synthesis complete",
            extra={"room_id": room_id, "run_id": run_id, "count": len(out)},
        )
        return normalize_findings(out, source_kind="cross_document_synthesis", limit=15)
