"""
Shared formatting utilities for PE diligence analysis output.

Consolidates duplicate formatting functions used across multiple synthesis modules.
"""
from typing import Dict, List

from app.verticals.private_equity.diligence.doc_types import DEFAULT_DOC_TYPE


def fmt_classifications(document_classifications: Dict[str, dict], multiline: bool = True) -> str:
    """
    Format document type classifications into a string summary.

    Args:
        document_classifications: Dict mapping doc_id to classification data
        multiline: If True, format as bullet list; if False, format as comma-separated inline

    Returns:
        Formatted string summary of document types and counts
    """
    if not document_classifications:
        return ""

    # Count documents by type
    counts: Dict[str, int] = {}
    for cls in document_classifications.values():
        dt = cls.get("document_type") or DEFAULT_DOC_TYPE
        counts[dt] = counts.get(dt, 0) + 1

    # Sort by count descending
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])

    if multiline:
        # Bullet list format (findings_synthesizer style)
        lines = ["## Document Types in Room"]
        for dt, cnt in sorted_counts:
            lines.append(f"- {dt}: {cnt} doc(s)")
        return "\n".join(lines)
    else:
        # Inline format (summary_generator style)
        parts = [f"{dt}: {n}" for dt, n in sorted_counts]
        return f"## Documents: {', '.join(parts)}"


def fmt_checklist_summary(checklist_entries: List[dict], detailed: bool = False) -> str:
    """
    Format checklist items into a string summary.

    Args:
        checklist_entries: List of checklist entries with 'item' key
        detailed: If True, show all gaps with status+priority; if False, show coverage ratio

    Returns:
        Formatted string summary of checklist coverage
    """
    if not checklist_entries:
        return ""

    items = [e["item"] for e in checklist_entries]

    if detailed:
        # Detailed format (findings_synthesizer style - focus on gaps)
        gaps = [it for it in items if it.get("status") in {"missing", "partial"}]
        if not gaps:
            return ""
        lines = ["## Checklist Gaps"]
        for item in gaps:
            lines.append(f"- [{item['status'].upper()}] {item['title']} (priority={item['priority']})")
        return "\n".join(lines)
    else:
        # Summary format (summary_generator style - coverage ratio)
        covered = sum(1 for it in items if it.get("status") in {"covered", "partial"})
        total = len(items)
        gaps = [it["title"] for it in items if it.get("status") == "missing"]
        lines = [f"## Checklist: {covered}/{total} covered"]
        if gaps:
            lines.append(f"Missing: {', '.join(gaps)}")
        return "\n".join(lines)
