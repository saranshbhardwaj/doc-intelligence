"""Per-document LLM analysis for PE diligence.

V2 (unified): Every classified document gets analyzed with:
  - Pre-computed clause signals (from CLAUSE_PATTERNS regex scan) as structured hints
  - Playbook-driven structured extraction targets combined into ONE LLM call
  - Section-type-aware hybrid retrieval (narrative vs table priority per doc type)
  - Sync chunk expansion (table↔narrative, continuations)
  - Amendment context injection (parent doc, amendment type, evidence quote)
  - Open-ended risk scan to catch anything playbooks miss

V1 (legacy Stage 6b): Only analyzes docs that regex missed (zero clause hits).
  Kept for backward-compat when pe_diligence_pipeline_v2=False.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.db_models_chat import DocumentChunk
from app.verticals.private_equity.diligence.normalization import normalize_findings
from app.utils.logging import logger
from app.verticals.private_equity.diligence.doc_types import DEFAULT_DOC_TYPE, PEDocumentType
from app.verticals.private_equity.diligence.playbook_seeds import (
    SYSTEM_PLAYBOOKS,
    SYSTEM_PLAYBOOKS_BY_SLUG,
    build_playbook_analysis_instruction,
)


# ─── Risk queries per document type ──────────────────────────────────────────

DOC_TYPE_RISK_QUERIES: Dict[str, str] = {
    PEDocumentType.PURCHASE_AGREEMENT.value: (
        "representations warranties indemnification cap basket survival "
        "material adverse change closing conditions termination fee earnout "
        "change of control assignment consent non-compete exclusivity "
        "escrow holdback purchase price adjustment working capital peg"
    ),
    PEDocumentType.MERGER_AGREEMENT.value: (
        "representations warranties indemnification cap basket survival "
        "material adverse change closing conditions termination fee earnout "
        "change of control assignment consent non-compete exclusivity "
        "escrow holdback purchase price adjustment working capital peg "
        "merger consideration regulatory approval fiduciary out matching rights go-shop"
    ),
    PEDocumentType.DISCLOSURE_SCHEDULE.value: (
        "disclosure schedule exceptions carve-out indemnification schedule "
        "material contracts litigation tax matters intellectual property employees "
        "change of control consents excluded liabilities"
    ),
    PEDocumentType.SHAREHOLDER_AGREEMENT.value: (
        "drag along tag along board rights voting agreement preemptive rights "
        "transfer restrictions right of first refusal co-sale liquidation preference "
        "protective provisions change of control"
    ),
    PEDocumentType.LEGAL_CONTRACT.value: (
        "termination penalty fee liability indemnification assignment consent "
        "change of control IP ownership non-compete confidentiality breach "
        "governing law dispute arbitration payment obligation auto-renewal "
        "limitation of liability consequential damages"
    ),
    PEDocumentType.CUSTOMER_CONTRACT.value: (
        "termination for convenience auto-renewal change of control assignment consent "
        "service level SLA breach cure period limitation of liability revenue share "
        "exclusivity MFN most favored nation indemnification IP ownership license"
    ),
    PEDocumentType.EMPLOYMENT_AGREEMENT.value: (
        "base salary severance non-compete non-solicitation equity vesting acceleration "
        "change of control at-will termination for cause key person golden parachute "
        "clawback bonus deferred compensation garden leave"
    ),
    PEDocumentType.IP_LICENSE.value: (
        "license grant scope exclusivity territory sublicense royalty IP assignment "
        "ownership change of control termination reversion source code escrow "
        "patent infringement warranty disclaimer indemnification"
    ),
    PEDocumentType.VENDOR_CONTRACT.value: (
        "supply termination change of control assignment exclusivity pricing "
        "minimum commitment concentration sole source force majeure "
        "indemnification liability cap delivery warranty"
    ),
    PEDocumentType.NDA.value: (
        "confidential information disclosure permitted use return of information "
        "breach injunctive relief term residuals carve-out "
        "reverse engineering standard of care"
    ),
    PEDocumentType.AMENDMENT.value: (
        "modified clause deleted superseded restated changed obligation "
        "new term effective date consideration amendment fee waiver "
        "consent required approval additional payment"
    ),
    PEDocumentType.FINANCIAL_STATEMENT.value: (
        "revenue EBITDA net income debt leverage interest coverage working capital "
        "cash flow operating loss going concern audit qualification contingent liability "
        "off-balance sheet related party transaction covenant breach deferred revenue "
        "accounts receivable aging bad debt pension obligation"
    ),
    PEDocumentType.QOE_REPORT.value: (
        "adjusted EBITDA normalization add-back non-recurring one-time item "
        "quality of earnings revenue recognition customer concentration "
        "working capital peg pro forma adjustment disputed item "
        "revenue pull-forward expense timing manipulation"
    ),
    PEDocumentType.OFFERING_MEMORANDUM.value: (
        "risk factor investment consideration competitive threat customer concentration "
        "regulatory risk key person dependency market risk technology obsolescence "
        "litigation pending regulatory investigation management dependency "
        "customer churn contract renewal risk"
    ),
    PEDocumentType.TAX_DOCUMENT.value: (
        "tax indemnity tax sharing transfer pricing section 382 net operating loss "
        "uncertain tax position sales tax nexus withholding tax audit"
    ),
    PEDocumentType.REGULATORY_FILING.value: (
        "regulatory filing sec investigation fda warning letter compliance matter "
        "government inquiry consent decree enforcement action"
    ),
    PEDocumentType.INSURANCE_DOCUMENT.value: (
        "insurance coverage policy limit retention deductible exclusion tail coverage "
        "representation and warranty insurance"
    ),
    PEDocumentType.CHARTER_DOCUMENT.value: (
        "certificate of incorporation bylaws voting rights preferred stock "
        "board composition anti-dilution liquidation preference"
    ),
    PEDocumentType.POLICY_DOCUMENT.value: (
        "policy procedure code of conduct privacy information security "
        "retention incident response compliance"
    ),
    PEDocumentType.OTHER.value: (
        "risk liability obligation payment termination penalty fee indemnification "
        "breach default material adverse change of control assignment"
    ),
}

def _build_doc_type_playbooks() -> Dict[str, List[str]]:
    routing: Dict[str, List[str]] = {doc_type.value: [] for doc_type in PEDocumentType}
    for playbook in SYSTEM_PLAYBOOKS:
        slug = playbook.get("slug")
        if not slug:
            continue
        for doc_type in playbook.get("applicable_doc_types") or []:
            if doc_type in routing and slug not in routing[doc_type]:
                routing[doc_type].append(slug)
    return routing


_DOC_TYPE_PLAYBOOKS: Dict[str, List[str]] = _build_doc_type_playbooks()


# ─── Pydantic output models ───────────────────────────────────────────────────


class DocFinding(BaseModel):
    # Core classification
    category: str = Field(description="contract | debt | commercial | ip | people | financial | risk | legal | spa | tax | regulatory | privacy | esg | insurance | governance | numeric_reconciliation | missing_clause")
    severity: str = Field(description="high | medium | low")

    # Analyst-facing fields — kept short by design (prompt enforces limits; truncation in _convert_findings)
    title: str = Field(description="≤70 chars. Active voice, include key number with currency as written in doc: 'Indemnification cap £2M (5% EV) — below market'")
    summary: str = Field(description="≤150 chars. ONE sentence: what the issue is and why it matters for this deal.")
    assessment: str = Field(description="standard | below_market | above_market | missing | non_standard | flagged")

    # Evidence
    evidence_quote: Optional[str] = Field(None, description="Verbatim clause text ≤280 chars. Exact words, not paraphrase.")
    page_number: Optional[int] = None

    # Scoring + structured extraction (used downstream by checklist + synthesizer)
    confidence: Optional[float] = Field(None, description="0.7–1.0. Certainty this finding is accurate and material. 0.95+ only if exact clause text is present.")
    playbook_slug: Optional[str] = None
    clause_type: Optional[str] = None
    extracted_fields: Optional[dict] = None  # e.g. {cap_amount: 2000000, cap_currency: "GBP", survival_months: 18}


class DocFindings(BaseModel):
    findings: List[DocFinding] = Field(default_factory=list)


# ─── System prompts ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT_V2 = """\
You are a PE diligence extraction engine — equivalent to Kira or Luminance smart-field extraction.
You review ONE document and output structured findings for a senior analyst.

─── EXTRACTION RULES ───────────────────────────────────────────────────────────
1. MAXIMUM 8 findings. If you identify more, keep only the most material.
   Priority: HIGH severity first → playbook extractions → open-ended risks.
2. SKIP routine and boilerplate — only flag what deviates from market standard
   or represents a real deal risk.
3. QUANTIFY everything: monetary amounts with the currency symbol as written in
   the document (£2M, €5M, $10M), periods in months, ratios as numbers.
   Put key numbers directly in the title.
4. Do NOT fabricate. If a clause is absent from the excerpts, omit it.
5. Do NOT write recommendations. The analyst knows what to do.
6. Use REGEX SIGNALS as hints — verify context before raising a finding.

─── FIELD GUIDE ────────────────────────────────────────────────────────────────
title       ≤70 chars, active voice, include the key number with currency:
            GOOD: "Indemnification cap £2M (5% EV) — below market"
            GOOD: "Change-of-control consent required from 3 counterparties"
            BAD:  "Indemnification Cap Analysis"

summary     ≤150 chars, ONE sentence — what the issue is and why it matters.
            GOOD: "Cap well below typical 10-15% of EV; material reps claims would exceed coverage."
            BAD:  "The indemnification cap limits the seller's liability. This is important because..."

assessment  Exactly one of:
            standard      — market-standard term, no action needed
            below_market  — weaker protection than typical (low cap, short survival, etc.)
            above_market  — seller-favourable, stronger than typical
            missing       — expected clause is absent from this document
            non_standard  — unusual or bespoke term needing review
            flagged       — needs legal/tax/specialist review regardless of market position

evidence_quote  Verbatim text from the excerpt that triggered this finding, ≤280 chars.
                Exact words only — do not paraphrase.

confidence  0.7–1.0. How certain you are this finding is accurate and material.
            Use 0.95+ only if the exact clause text is present and unambiguous.

severity    high   = deal-breaker or IC-level risk, blocks or reprices the deal
            medium = requires negotiation or advisor attention before close
            low    = for information only, no immediate action

─── OUTPUT FORMAT ───────────────────────────────────────────────────────────────
Return JSON matching this structure exactly:
{"findings": [
  {
    "category": "contract",
    "severity": "high",
    "title": "Indemnification cap £2M (5% EV) — below market",
    "summary": "Cap well below typical 10-15% of EV; material reps claims would exceed coverage.",
    "assessment": "below_market",
    "evidence_quote": "the aggregate liability of Seller shall not exceed Two Million Pounds (£2,000,000)",
    "page_number": 14,
    "confidence": 0.96,
    "playbook_slug": "spa_core",
    "clause_type": "indemnification_cap",
    "extracted_fields": {"cap_amount": 2000000, "cap_currency": "GBP", "cap_pct_ev": 0.05, "survival_months": 18}
  }
]}
"""


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_playbook_section(doc_type: str) -> str:
    """Build the ═══ PLAYBOOKS TO APPLY ═══ section for a doc_type."""
    slugs = _DOC_TYPE_PLAYBOOKS.get(doc_type, [])
    if not slugs:
        return ""
    lines = ["═══ PLAYBOOKS TO APPLY ═══", ""]
    for slug in slugs:
        playbook = SYSTEM_PLAYBOOKS_BY_SLUG.get(slug)
        if playbook:
            lines.append(build_playbook_analysis_instruction(playbook))
            lines.append("")
    return "\n".join(lines)


def _build_signals_section(clause_signals: List[dict]) -> str:
    """Build the ═══ REGEX SIGNALS DETECTED ═══ section."""
    if not clause_signals:
        return ""
    lines = ["═══ REGEX SIGNALS DETECTED ═══"]
    for s in clause_signals[:20]:  # cap at 20 signals
        page = s.get("page_number")
        page_str = f" (p.{page})" if page else ""
        snippet = (s.get("snippet") or "")[:120].replace("\n", " ")
        lines.append(f"- {s['clause_type']}{page_str}: \"{snippet}\"")
    return "\n".join(lines)


def _build_amendment_section(amendment_link: Optional[dict]) -> str:
    """Build the ═══ AMENDMENT CONTEXT ═══ section for amendment docs."""
    if not amendment_link or not amendment_link.get("parent_document_id"):
        return ""
    parent_filename = amendment_link.get("parent_filename", amendment_link.get("parent_document_id", "unknown"))
    amendment_type = amendment_link.get("amendment_type", "modifies")
    evidence = (amendment_link.get("evidence_quote") or "")[:200]
    lines = [
        "═══ AMENDMENT CONTEXT ═══",
        f"This document {amendment_type} → {parent_filename}",
        f'Reference quote: "{evidence}"',
        "",
        "AMENDMENT ANALYSIS FOCUS: Extract WHAT changed. For each clause:",
        "- What was the original provision?",
        "- What is the new/modified provision?",
        "- What was deleted or added?",
        "- Net impact on deal economics, risk, or obligations?",
    ]
    return "\n".join(lines)


def _expand_chunks_sync(db: Any, chunks: List[dict]) -> List[dict]:
    """Sync chunk expansion: fetch linked narrative/table/parent chunks in one batch query."""
    expansion_ids: Set[str] = set()
    expansion_map: Dict[str, List[tuple]] = {}

    for chunk in chunks:
        chunk_id = str(chunk["id"])
        metadata = chunk.get("chunk_metadata") or {}
        expansion_map[chunk_id] = []

        # Tables → linked narrative
        if metadata.get("linked_narrative_id"):
            tid = str(metadata["linked_narrative_id"])
            expansion_ids.add(tid)
            expansion_map[chunk_id].append((tid, "table_context"))

        # Continuations → parent
        if metadata.get("is_continuation") and metadata.get("parent_chunk_id"):
            pid = str(metadata["parent_chunk_id"])
            expansion_ids.add(pid)
            expansion_map[chunk_id].append((pid, "continuation_parent"))

    if not expansion_ids:
        return chunks

    try:
        rows = db.execute(
            select(DocumentChunk).where(DocumentChunk.id.in_(list(expansion_ids)))
        ).scalars().all()
        fetched = {
            str(r.id): {
                "id": str(r.id),
                "document_id": r.document_id,
                "text": r.text,
                "page_number": r.page_number,
                "is_tabular": r.is_tabular,
                "section_heading": r.section_heading,
                "section_type": r.section_type,
                "chunk_metadata": r.chunk_metadata or {},
            }
            for r in rows
        }
    except Exception as exc:
        logger.warning("Chunk expansion batch fetch failed", extra={"error": str(exc)[:200]})
        return chunks

    expanded: List[dict] = []
    seen: Set[str] = {str(chunk["id"]) for chunk in chunks}

    for chunk in chunks:
        expanded.append(chunk)
        chunk_id = str(chunk["id"])
        for target_id, reason in expansion_map.get(chunk_id, []):
            if target_id not in seen and target_id in fetched:
                ec = fetched[target_id].copy()
                ec["_expansion_reason"] = reason
                ec["_expanded_from"] = chunk_id
                expanded.append(ec)
                seen.add(target_id)

    return expanded


def _build_v2_user_content(
    filename: str,
    doc_type: str,
    clause_signals: List[dict],
    chunks: List[dict],
    amendment_link: Optional[dict] = None,
) -> str:
    """Assemble the V2 per-doc user prompt."""
    parts = [f"Document: {filename} (type: {doc_type})", ""]

    playbook_section = _build_playbook_section(doc_type)
    if playbook_section:
        parts.append(playbook_section)

    amendment_section = _build_amendment_section(amendment_link)
    if amendment_section:
        parts.append(amendment_section)
        parts.append("")

    signals_section = _build_signals_section(clause_signals)
    if signals_section:
        parts.append(signals_section)
        parts.append("")

    parts.append("═══ DOCUMENT EXCERPTS ═══")
    for i, chunk in enumerate(chunks, 1):
        page = chunk.get("page_number") or "?"
        section_type = chunk.get("section_type") or "narrative"
        expansion = f" [expanded: {chunk['_expansion_reason']}]" if chunk.get("_expansion_reason") else ""
        text = (chunk.get("text") or "")[:400]
        parts.append(f"[Excerpt {i}, p.{page}, {section_type}{expansion}]\n{text}")

    parts.append("")
    parts.append("═══ OPEN-ENDED SCAN ═══")
    parts.append(
        "Also flag any material risks, unusual terms, or missing standard protections "
        "not already captured by the playbooks above."
    )

    return "\n\n".join(parts)


# ─── Main class ───────────────────────────────────────────────────────────────


class PerDocumentAnalyzer:
    """Analyzes individual documents with playbook-driven + open-ended LLM analysis."""

    def __init__(self, db: Any, runner: Optional[StructuredLLMRunner] = None):
        self.db = db
        if runner is None:
            llm_client = LLMClient(
                api_key=settings.anthropic_api_key,
                model=settings.synthesis_llm_model,
                max_tokens=8192,
                max_input_chars=settings.llm_max_input_chars,
                timeout_seconds=settings.synthesis_llm_timeout_seconds,
            )
            runner = StructuredLLMRunner(llm_client)
        self.runner = runner

    # ── V2: Analyze ALL documents ────────────────────────────────────────────

    async def analyze_all_documents(
        self,
        *,
        doc_ids_with_classifications: Dict[str, dict],
        clause_signals_by_doc: Dict[str, List[dict]],
        amendment_links: Dict[str, Any],  # doc_id -> AmendmentLinkCandidate or dict
        room_id: str,
        run_id: str,
    ) -> List[dict]:
        """V2: Analyze every classified document. Returns list of pipeline finding dicts."""
        if not doc_ids_with_classifications:
            return []

        semaphore = asyncio.Semaphore(settings.pe_diligence_per_doc_analysis_concurrency)

        tasks = [
            self._analyze_one_v2(
                doc_id=doc_id,
                doc_type=cls.get("document_type", DEFAULT_DOC_TYPE),
                filename=cls.get("filename", doc_id[:8]),
                clause_signals=clause_signals_by_doc.get(doc_id, []),
                amendment_link=self._extract_link_dict(amendment_links.get(doc_id)),
                semaphore=semaphore,
                room_id=room_id,
                run_id=run_id,
            )
            for doc_id, cls in doc_ids_with_classifications.items()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_findings: List[dict] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    f"V2 per-doc analysis failed for one doc: {result!r}",
                    extra={"room_id": room_id, "run_id": run_id, "error": str(result)[:200]},
                )
                continue
            all_findings.extend(result)

        logger.info(
            "V2 per-doc analysis complete",
            extra={
                "room_id": room_id,
                "run_id": run_id,
                "docs_analyzed": len(doc_ids_with_classifications),
                "total_findings": len(all_findings),
            },
        )
        return all_findings

    def _extract_link_dict(self, link: Any) -> Optional[dict]:
        """Convert AmendmentLinkCandidate or dict to dict, or None."""
        if link is None:
            return None
        if isinstance(link, dict):
            return link
        # AmendmentLinkCandidate pydantic model
        if hasattr(link, "model_dump"):
            return link.model_dump()
        if hasattr(link, "dict"):
            return link.dict()
        return None

    async def _analyze_one_v2(
        self,
        *,
        doc_id: str,
        doc_type: str,
        filename: str,
        clause_signals: List[dict],
        amendment_link: Optional[dict],
        semaphore: asyncio.Semaphore,
        room_id: str,
        run_id: str,
    ) -> List[dict]:
        async with semaphore:
            from app.core.rag.hybrid_retriever import HybridRetriever
            from app.services.service_locator import get_reranker

            risk_query = DOC_TYPE_RISK_QUERIES.get(doc_type, DOC_TYPE_RISK_QUERIES[DEFAULT_DOC_TYPE])
            retriever = HybridRetriever(self.db)

            # Fetch more chunks than needed for reranking headroom
            fetch_k = settings.pe_diligence_per_doc_rerank_fetch_k
            top_k = settings.pe_diligence_per_doc_analysis_top_k
            chunks = retriever.retrieve(
                query=risk_query,
                document_ids=[doc_id],
                top_k=fetch_k,
            )

            if not chunks:
                logger.info(
                    "V2 per-doc: no chunks found for doc, skipping",
                    extra={"doc_id": doc_id, "doc_type": doc_type, "room_id": room_id},
                )
                return []

            # Rerank with CrossEncoder, then take top_k best chunks
            if len(chunks) > top_k:
                try:
                    reranker = get_reranker()
                    if reranker:
                        chunks = reranker.rerank(risk_query, chunks, top_k=top_k)
                    else:
                        chunks = chunks[:top_k]
                except Exception as rerank_exc:
                    logger.warning(
                        "V2 per-doc: reranking failed, truncating to top_k",
                        extra={"doc_id": doc_id, "error": str(rerank_exc)[:200]},
                    )
                    chunks = chunks[:top_k]

            # Expand linked chunks (table↔narrative, continuations)
            chunks = _expand_chunks_sync(self.db, chunks)

            # Build prompt and call LLM
            # _SYSTEM_PROMPT_V2 is static — eligible for Anthropic prompt caching across all docs
            user_content = _build_v2_user_content(
                filename=filename,
                doc_type=doc_type,
                clause_signals=clause_signals,
                chunks=chunks,
                amendment_link=amendment_link,
            )

            try:
                result = await self.runner.run_structured(
                    user_content=user_content,
                    system_prompt=_SYSTEM_PROMPT_V2,
                    pydantic_model=DocFindings,
                    use_cache=True,  # static system prompt → cache hits after first doc call
                )
            except Exception as exc:
                logger.warning(
                    f"V2 per-doc LLM call failed: {exc!r}",
                    extra={"doc_id": doc_id, "room_id": room_id, "error": str(exc)[:200]},
                )
                return []

            raw_findings = (result.get("data") or {}).get("findings") or []
            out = self._convert_findings(raw_findings, doc_id, doc_type, filename, engine="per_doc_llm_v2")

            logger.info(
                "V2 per-doc analysis complete for doc",
                extra={
                    "doc_id": doc_id,
                    "doc_type": doc_type,
                    "doc_filename": filename,
                    "findings": len(out),
                    "signals": len(clause_signals),
                    "chunks": len(chunks),
                    "room_id": room_id,
                },
            )
            return out

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _convert_findings(
        self,
        raw_findings: List[Any],
        doc_id: str,
        doc_type: str,
        filename: str,
        engine: str,
    ) -> List[dict]:
        """Convert raw LLM finding dicts to pipeline finding dicts. Cap at 8 findings."""
        out: List[dict] = []
        for raw in raw_findings[:8]:  # enforce max 8 here, not in pydantic schema
            if not isinstance(raw, dict):
                continue
            out.append({
                "category": raw.get("category", "contract"),
                "severity": raw.get("severity", "medium"),
                "title": (raw.get("title") or "")[:200],
                # V2 schema uses "summary" (≤150 chars); stored as "description" for DB/synthesizer compat
                "description": (raw.get("summary") or raw.get("description") or "")[:500],
                "recommendation": "",
                "status": "open",
                "source_document_id": doc_id,
                "source_chunk_id": None,
                "source_page_number": raw.get("page_number"),
                "evidence_quote": (raw.get("evidence_quote") or "")[:300],
                "confidence": raw.get("confidence"),
                "metadata_json": {
                    "engine": engine,
                    "doc_type": doc_type,
                    "filename": filename,
                    "assessment": raw.get("assessment"),
                    "playbook_slug": raw.get("playbook_slug"),
                    "extracted_fields": raw.get("extracted_fields") or {},
                    "clause_type": raw.get("clause_type"),
                },
                "evidence_list": [],
            })
        return normalize_findings(out, source_kind="per_document", limit=8)
