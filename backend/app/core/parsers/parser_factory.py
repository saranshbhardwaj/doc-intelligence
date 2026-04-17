# backend/app/services/parsers/parser_factory.py
"""Factory for creating the document parser."""
from .base import DocumentParser
from .azure_document_intelligence_parser import AzureDocumentIntelligenceParser
from app.config import settings
from app.utils.logging import logger


class ParserFactory:
    """Factory to create the document parser.

    All documents are parsed with Azure Document Intelligence, which handles
    both digital and scanned PDFs natively.

    Testing Override:
    - FORCE_PARSER env var: Force a specific parser by name
    """

    @classmethod
    def get_parser(cls) -> DocumentParser:
        """Get the Azure Document Intelligence parser.

        Returns:
            DocumentParser instance

        Raises:
            ValueError: If FORCE_PARSER specifies an unknown parser name
        """
        if settings.force_parser:
            logger.warning(f"TESTING MODE: Forcing parser={settings.force_parser}")
            return cls._create_parser(settings.force_parser)

        return AzureDocumentIntelligenceParser(
            endpoint=settings.azure_doc_intelligence_endpoint or None,
            api_key=settings.azure_doc_intelligence_api_key or None,
            model_name=settings.azure_doc_model or None,
            timeout_seconds=settings.azure_doc_timeout_seconds or None,
        )

    @classmethod
    def _create_parser(cls, parser_name: str) -> DocumentParser:
        """Create parser instance by name (used for FORCE_PARSER override).

        Args:
            parser_name: Parser identifier

        Returns:
            DocumentParser instance

        Raises:
            ValueError: If parser name is unknown
        """
        if parser_name in ("azure_document_intelligence", "azure_doc_intelligence", "azure_docai"):
            return AzureDocumentIntelligenceParser(
                endpoint=settings.azure_doc_intelligence_endpoint or None,
                api_key=settings.azure_doc_intelligence_api_key or None,
                model_name=settings.azure_doc_model or None,
                timeout_seconds=settings.azure_doc_timeout_seconds or None,
            )

        raise ValueError(f"Unknown parser: {parser_name}")
