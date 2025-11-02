"""Factory for selecting appropriate chunker based on parser output."""

from typing import Optional

from app.services.chunkers.base import DocumentChunker
from app.services.chunkers.azure_chunker import AzurePageWiseChunker
from app.utils.logging import logger


class ChunkerFactory:
    """Factory for creating document chunkers based on parser type.

    Maps parser names to appropriate chunking strategies.
    """

    # Registry of chunkers by parser name
    _CHUNKER_REGISTRY = {
        "azure_document_intelligence": AzurePageWiseChunker,
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
        chunker_class = cls._CHUNKER_REGISTRY.get(parser_name)

        if not chunker_class:
            logger.warning(
                f"No chunker available for parser '{parser_name}'. "
                "Falling back to direct LLM processing (no chunking)."
            )
            return None

        logger.info(f"Using chunker: {chunker_class.__name__} for parser: {parser_name}")
        return chunker_class()

    @classmethod
    def supports_chunking(cls, parser_name: str) -> bool:
        """Check if chunking is supported for the given parser.

        Args:
            parser_name: Name of the parser

        Returns:
            True if chunking is available for this parser
        """
        return parser_name in cls._CHUNKER_REGISTRY

    @classmethod
    def register_chunker(cls, parser_name: str, chunker_class: type) -> None:
        """Register a new chunker for a parser (for extensions/testing).

        Args:
            parser_name: Name of the parser
            chunker_class: Chunker class (subclass of DocumentChunker)
        """
        cls._CHUNKER_REGISTRY[parser_name] = chunker_class
        logger.info(f"Registered chunker {chunker_class.__name__} for parser {parser_name}")
