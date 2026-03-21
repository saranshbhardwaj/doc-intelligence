"""Template registry for diligence investigations.

Each template defines the retrieval and analysis parameters for one
investigation type.  Seed queries drive the HybridRetriever; they are
the primary lever for recall — more diverse queries means more diverse
chunks are surfaced for claim building.

Adding a new investigation type:
  1. Add an entry to INVESTIGATION_TEMPLATES with seed_queries, hints, etc.
  2. Create a corresponding claim builder function in claim_builder.py.
  3. Wire the builder in tasks.py.
"""
from __future__ import annotations

from typing import Dict

from app.verticals.private_equity.diligence.doc_types import HIGH_VALUE_CONTRACT_DOC_TYPES


INVESTIGATION_TEMPLATES: Dict[str, dict] = {
    "change_of_control_exposure": {
        "title": "Change-of-Control Exposure",
        "default_question": (
            "Do contracts in this data room create change-of-control "
            "consent or termination risk?"
        ),
        # ── Seed queries ──────────────────────────────────────────
        # Each query is sent independently to HybridRetriever.
        # Dedup by chunk_id (keep highest score) happens in retriever.
        # Target: ~15 queries — diverse enough for recall, bounded
        # to keep latency reasonable (each query = one retriever call).
        "seed_queries": [
            # Core CoC terms
            "change of control",
            "change of control provision",
            "assignment consent",
            "consent required transfer",
            "termination upon change of control",
            "anti-assignment",
            # Legal synonyms the original 5 queries missed
            "novation rights obligations",
            "successor in interest",
            "transfer of controlling interest",
            "merger or consolidation",
            "sale of substantially all assets",
            # Restriction / prohibition language
            "assignment restriction prohibition",
            "prior written consent assignment",
            # Termination and penalty exposure
            "material adverse change default",
            "termination penalty liquidated damages",
            "acceleration upon default",
        ],
        # ── Document routing hints ────────────────────────────────
        "document_type_hints": [*sorted(HIGH_VALUE_CONTRACT_DOC_TYPES), "other"],
        "filename_hints": [
            "agreement",
            "contract",
            "msa",
            "license",
            "purchase",
            "amendment",
            "addendum",
            "lease",
            "service",
            "subscription",
        ],
    },
}


def get_template(investigation_type: str) -> dict:
    """Return the template dict for an investigation type.

    Raises ValueError if the type is not registered.
    """
    template = INVESTIGATION_TEMPLATES.get(investigation_type)
    if not template:
        raise ValueError(f"Unsupported investigation_type: {investigation_type}")
    return template
