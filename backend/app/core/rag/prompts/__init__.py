"""Versioned prompt registry for RAG chat."""

from app.config import settings

from .base import RagPromptSet
from .v1 import V1RagPromptSet

_REGISTRY: dict[str, type[RagPromptSet]] = {
    "v1": V1RagPromptSet,
}


def get_rag_prompt_set(version: str | None = None) -> RagPromptSet:
    """Return a RagPromptSet instance for the given version.

    Falls back to ``settings.rag_prompt_version`` when *version* is None.
    """
    v = version or settings.rag_prompt_version
    cls = _REGISTRY.get(v)
    if not cls:
        raise ValueError(f"Unknown RAG prompt version: {v!r}. Available: {list(_REGISTRY)}")
    return cls()
