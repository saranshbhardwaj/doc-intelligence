"""Base classes for versioned prompt sets."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Type

from pydantic import BaseModel


@dataclass
class PromptPair:
    """A system prompt + user message pair for a single LLM call."""

    system_prompt: str
    user_message: str
    response_model: Type[BaseModel]


class PromptSet(ABC):
    """Interface for a versioned set of template-fill prompts.

    Each concrete version (v1, v2, …) implements prompt construction
    and owns the Pydantic response models that are coupled to its prompts.
    """

    version: str

    # -- Stage 1: field detection ------------------------------------------

    @abstractmethod
    def build_detect_fields(self, pdf_context: str) -> PromptPair:
        """Build prompt for Stage 1 field detection from PDF chunks.

        system_prompt is empty string — the entire prompt goes in the user
        message, matching the existing single-message call site.
        """

    # -- Stage 2: targeted schema field extraction -------------------------

    @abstractmethod
    def build_extract_schema_fields(
        self,
        pdf_fields_json: str,
        unmapped_fields: List[Dict[str, Any]],
    ) -> PromptPair:
        """Build prompts for extracting YAML-schema field values from Azure DI data."""

    # -- Stage 2: targeted schema table extraction (single table, RAG) -----

    @abstractmethod
    def build_extract_table_values_rag_single(
        self,
        context_json: str,
        table_request: Dict[str, Any],
    ) -> PromptPair:
        """Build prompts for RAG-based single-table extraction."""

    # -- Stage 2: targeted schema table extraction (batch, RAG) -----------

    @abstractmethod
    def build_extract_table_values_rag(
        self,
        context_json: str,
        table_requests: List[Dict[str, Any]],
        header_equivalents: str,
    ) -> PromptPair:
        """Build prompts for extracting table row values via RAG chunks (batch)."""

