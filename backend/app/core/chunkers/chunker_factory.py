"""Factory for selecting appropriate chunker based on parser output."""

from typing import Optional

from app.core.chunkers.base import DocumentChunker
from app.core.chunkers.azure_chunker import AzurePageWiseChunker
from app.core.chunkers.azure_smart_chunker import AzureSmartChunker
from app.utils.logging import logger


class ChunkerFactory:
    """Factory for creating document chunkers based on parser type.

    Maps parser names to appropriate chunking strategies.
    """

    # Registry of chunkers by parser name
    _CHUNKER_REGISTRY = {
        "azure_document_intelligence": AzureSmartChunker,  # Smart chunker (default)
        # Legacy chunker (page-wise) - available but not default
        "azure_document_intelligence_pagewise": AzurePageWiseChunker,
        # Future chunkers:
        # "google_documentai": GooglePageWiseChunker,
        # "llmwhisperer": LLMWhispererChunker,
        # "pymupdf": PyMuPDFChunker,
    }

    @classmethod
    def get_chunker(cls, parser_name: str) -> Optional[DocumentChunker]:
        """Get appropriate chunker for the given parser.

        Args:
            parser_name: Name of the parser (e.g., 'azure_document_intelligence')

        Returns:
            DocumentChunker instance, or None if no chunker available

        Note:
            If no specific chunker is available, returns None.
            Caller should fall back to no-chunking (direct LLM call).
        """
        # Edge case: Validate parser_name is not None or empty
        if not parser_name or not isinstance(parser_name, str):
            logger.warning(
                f"Invalid parser_name: {parser_name} (expected non-empty string). "
                "Falling back to direct LLM processing (no chunking)."
            )
            return None

        if not parser_name.strip():
            logger.warning(
                "Empty parser_name provided. "
                "Falling back to direct LLM processing (no chunking)."
            )
            return None

        chunker_class = cls._CHUNKER_REGISTRY.get(parser_name)

        if not chunker_class:
            logger.warning(
                f"No chunker available for parser '{parser_name}'. "
                "Falling back to direct LLM processing (no chunking)."
            )
            return None

        # Edge case: Validate chunker_class can be instantiated
        try:
            logger.info(f"Using chunker: {chunker_class.__name__} for parser: {parser_name}")
            return chunker_class()
        except Exception as e:
            logger.error(
                f"Failed to instantiate chunker {chunker_class.__name__}: {e}",
                exc_info=True
            )
            return None

    @classmethod
    def supports_chunking(cls, parser_name: str) -> bool:
        """Check if chunking is supported for the given parser.

        Args:
            parser_name: Name of the parser

        Returns:
            True if chunking is available for this parser
        """
        # Edge case: Validate parser_name
        if not parser_name or not isinstance(parser_name, str):
            return False

        return parser_name in cls._CHUNKER_REGISTRY

    @classmethod
    def register_chunker(cls, parser_name: str, chunker_class: type) -> None:
        """Register a new chunker for a parser (for extensions/testing).

        Args:
            parser_name: Name of the parser
            chunker_class: Chunker class (subclass of DocumentChunker)

        Raises:
            ValueError: If inputs are invalid
        """
        # Edge case: Validate parser_name
        if not parser_name or not isinstance(parser_name, str):
            raise ValueError(f"Invalid parser_name: {parser_name} (expected non-empty string)")

        if not parser_name.strip():
            raise ValueError("parser_name cannot be empty string")

        # Edge case: Validate chunker_class
        if not chunker_class:
            raise ValueError("chunker_class cannot be None")

        if not isinstance(chunker_class, type):
            raise ValueError(f"chunker_class must be a class, got {type(chunker_class).__name__}")

        # Edge case: Validate chunker_class is subclass of DocumentChunker
        if not issubclass(chunker_class, DocumentChunker):
            raise ValueError(
                f"chunker_class must be a subclass of DocumentChunker, "
                f"got {chunker_class.__name__}"
            )

        cls._CHUNKER_REGISTRY[parser_name] = chunker_class
        logger.info(f"Registered chunker {chunker_class.__name__} for parser {parser_name}")
