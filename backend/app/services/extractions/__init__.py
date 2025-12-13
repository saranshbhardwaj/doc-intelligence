"""Extraction module - CIM extraction with summarization and table metrics.

This module contains all extraction-specific logic:
- Prompts (CIM extraction, batch summarization)
- Pipeline (extraction orchestration)
- Helpers (extraction utilities)
"""

from app.services.extractions.prompts import (
    CIM_EXTRACTION_SYSTEM_PROMPT,
    BATCH_SUMMARY_PROMPT_TEMPLATE,
    create_extraction_prompt,
    create_batch_summary_prompt,
)

__all__ = [
    "CIM_EXTRACTION_SYSTEM_PROMPT",
    "BATCH_SUMMARY_PROMPT_TEMPLATE",
    "create_extraction_prompt",
    "create_batch_summary_prompt",
]
