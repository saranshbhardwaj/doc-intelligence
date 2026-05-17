"""OM structure artifact building for template fill runs."""

import copy
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Tuple

from app.services.citations import normalize_citations
from app.verticals.real_estate.template_filling.source_map import STRUCTURE_LOW_CONFIDENCE


def iter_structure_entries(structure: Dict[str, Any]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    for group_name in ("column_map", "section_presence"):
        group = structure.get(group_name) or {}
        for key, value in group.items():
            if isinstance(value, dict):
                yield f"{group_name}.{key}", value


def build_structure_confidence_summary(structure: Dict[str, Any]) -> Dict[str, Any]:
    entries = list(iter_structure_entries(structure or {}))
    confidences = [
        float(entry.get("confidence"))
        for _, entry in entries
        if entry.get("confidence") is not None
    ]
    if not confidences:
        return {
            "min_confidence": None,
            "mean_confidence": None,
            "low_confidence_keys": [],
        }
    return {
        "min_confidence": round(min(confidences), 4),
        "mean_confidence": round(sum(confidences) / len(confidences), 4),
        "low_confidence_keys": [
            key
            for key, entry in entries
            if float(entry.get("confidence") or 0) < STRUCTURE_LOW_CONFIDENCE
        ],
    }


def build_om_structure_artifact(
    detected_structure: Dict[str, Any],
    model_name: str,
) -> Dict[str, Any]:
    """Build the stored Source Map artifact used by this fill run."""
    normalized_structure = copy.deepcopy(detected_structure)
    for bucket in ("column_map", "section_presence"):
        for entry in (normalized_structure.get(bucket) or {}).values():
            if isinstance(entry, dict):
                raw_citations = []
                for citation in entry.get("citations", []) or []:
                    citation_text = str(citation).strip()
                    if re.fullmatch(r"(?:S|D)\d+:p\d+", citation_text):
                        citation_text = f"[{citation_text}]"
                    raw_citations.append(citation_text)
                entry["citations"] = normalize_citations(raw_citations)
    return {
        "extractor_version": "template_om_structure_v1",
        "model_name": model_name,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "edited": False,
        "original": copy.deepcopy(normalized_structure),
        "effective": copy.deepcopy(normalized_structure),
        "confidence_summary": build_structure_confidence_summary(normalized_structure),
    }
