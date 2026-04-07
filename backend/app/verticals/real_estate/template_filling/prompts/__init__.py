"""Versioned prompt registry for RE template filling."""

from app.config import settings

from .base import PromptPair as PromptPair, PromptSet
from .v1 import (
    V1PromptSet,
    # Pydantic response models — explicit re-exports for downstream imports
    AutoMappingResult as AutoMappingResult,
    DetectedField as DetectedField,
    ExtractedFieldValue as ExtractedFieldValue,
    FieldDetectionResult as FieldDetectionResult,
    FieldMapping as FieldMapping,
    SchemaFieldExtractionResult as SchemaFieldExtractionResult,
    SchemaFieldResult as SchemaFieldResult,
    SchemaTableExtractionResult as SchemaTableExtractionResult,
    SchemaTableResult as SchemaTableResult,
    SchemaTableRowResult as SchemaTableRowResult,
)

_REGISTRY: dict[str, type[PromptSet]] = {
    "v1": V1PromptSet,
}


def get_prompt_set(version: str | None = None) -> PromptSet:
    """Return a PromptSet instance for the given version.

    Falls back to ``settings.re_template_prompt_version`` when *version* is None.
    """
    v = version or settings.re_template_prompt_version
    cls = _REGISTRY.get(v)
    if not cls:
        raise ValueError(f"Unknown prompt version: {v!r}. Available: {list(_REGISTRY)}")
    return cls()
