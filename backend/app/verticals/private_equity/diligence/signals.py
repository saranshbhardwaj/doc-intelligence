"""Signal extraction helpers for PE diligence analysis."""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Dict, List, Optional
import re

from app.db_models_chat import DocumentChunk

from app.verticals.private_equity.diligence.rules import (
    CLAUSE_META,
    CLAUSE_PATTERNS,
    METRIC_PATTERNS,
    MULTIPLIERS,
)

_CURRENCY_RE = re.compile(
    r"[$£€¥₹₩₺₽₣₦₴₸₫₱]"
    r"|(?<![A-Z])(?:USD|GBP|EUR|JPY|CHF|CAD|AUD|HKD|SGD|NZD|SEK|NOK|DKK|INR|CNY|RMB|BRL|MXN|ZAR|KRW|TWD|THB|AED|SAR|ILS)(?![A-Z])",
    re.ASCII,
)


def row_dicts(rows: List[tuple]) -> List[dict]:
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


def clip_quote(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].strip().replace("\n", " ")


def make_evidence(
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


def extract_clause_hits(rows: List[dict]) -> List[dict]:
    hits = []
    for row in rows:
        text = row["text"]
        for clause_type, pattern in CLAUSE_PATTERNS.items():
            for match in pattern.finditer(text):
                start, end = match.span()
                quote = clip_quote(text, start, end)
                hits.append(
                    {
                        "clause_type": clause_type,
                        "evidence": make_evidence(
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


def normalize_numeric(value_text: str, unit_text: Optional[str]) -> Optional[float]:
    try:
        base = float(value_text.replace(",", ""))
    except Exception:
        return None
    mult = MULTIPLIERS.get((unit_text or "").strip().lower() or None, 1.0)
    return base * mult


def extract_numeric_signals(rows: List[dict]) -> Dict[str, List[dict]]:
    signals: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        text = row["text"]
        for metric, pattern in METRIC_PATTERNS.items():
            for match in pattern.finditer(text):
                span = match.span()
                value_text = match.group(2)
                unit_text = match.group(3)
                value = normalize_numeric(value_text, unit_text)
                if value is None:
                    continue
                has_unit = unit_text is not None
                if not has_unit:
                    window = text[max(0, span[0] - 20):span[1]]
                    if not _CURRENCY_RE.search(window):
                        continue
                quote = clip_quote(text, span[0], span[1])
                signals[metric].append(
                    {
                        "value": value,
                        "evidence": make_evidence(
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


def build_numeric_reconciliation_findings(signals: Dict[str, List[dict]]) -> List[dict]:
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
    if revenue_vals and ebitda_vals and median(ebitda_vals) > median(revenue_vals):
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
