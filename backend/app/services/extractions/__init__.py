"""Extraction module - DEPRECATED.

⚠️ BACKWARD COMPATIBILITY SHIM ⚠️
This module has been moved to: app.verticals.private_equity.extraction

This file re-exports from the new location to maintain backward compatibility.
Please update your imports to use the new location:
    from app.verticals.private_equity.extraction import ...
"""

from app.verticals.private_equity.extraction.prompts import (
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
