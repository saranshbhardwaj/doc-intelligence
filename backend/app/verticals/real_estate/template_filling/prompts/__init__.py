"""Versioned prompt registry for RE template filling."""

from app.config import settings

from .base import PromptPair, PromptSet
from .v1 import (
    V1PromptSet,
    # Pydantic response models
    AutoMappingResult,
    DetectedField,
    ExtractedFieldValue,
    FieldDetectionResult,
    FieldMapping,
    SchemaFieldExtractionResult,
    SchemaFieldResult,
    SchemaTableExtractionResult,
    SchemaTableResult,
    SchemaTableRowResult,
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
