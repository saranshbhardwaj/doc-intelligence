# backend/app/services/parsers/parser_factory.py
"""Factory for selecting the appropriate parser based on user tier and PDF type"""
from typing import Optional, Dict
from .base import DocumentParser
from .pymupdf_parser import PyMuPDFParser
from .google_documentai_parser import GoogleDocumentAIParser
from .azure_document_intelligence_parser import AzureDocumentIntelligenceParser
from app.config import settings
from app.utils.logging import logger


class ParserFactory:
    """Factory to create the appropriate parser based on user tier and PDF type

    Parser strategy is now configurable via environment variables.
    See config.py for parser_*_digital and parser_*_scanned settings.

    Default Strategy:
    - Free tier:
        - Digital PDF → PyMuPDF (free, fast)
        - Scanned PDF → Reject (upgrade prompt)

    - Pro tier:
        - Digital PDF → PyMuPDF (free, fast)
        - Scanned PDF → LLMWhisperer (paid OCR)

    - Enterprise tier:
        - Digital PDF → LLMWhisperer (consistent quality)
        - Scanned PDF → LLMWhisperer

    Testing Overrides:
    - FORCE_PARSER: Force specific parser for all requests
    - FORCE_USER_TIER: Force specific tier for all requests
    """

    @classmethod
    def _load_parser_config(cls) -> Dict[str, Dict[str, Optional[str]]]:
        """Load parser configuration from settings

        Returns:
            Dict mapping tier -> pdf_type -> parser_name
        """
        return {
            "free": {
                "digital": settings.parser_free_digital if settings.parser_free_digital != "none" else None,
                "scanned": settings.parser_free_scanned if settings.parser_free_scanned != "none" else None
            },
            "pro": {
                "digital": settings.parser_pro_digital if settings.parser_pro_digital != "none" else None,
                "scanned": settings.parser_pro_scanned if settings.parser_pro_scanned != "none" else None
            },
            "enterprise": {
                "digital": settings.parser_enterprise_digital if settings.parser_enterprise_digital != "none" else None,
                "scanned": settings.parser_enterprise_scanned if settings.parser_enterprise_scanned != "none" else None
            }
        }

    @classmethod
    def get_parser(cls, user_tier: str, pdf_type: str) -> Optional[DocumentParser]:
        """Get the appropriate parser for user tier and PDF type

        Args:
            user_tier: User tier ('free', 'pro', 'enterprise')
            pdf_type: PDF type ('digital' or 'scanned')

        Returns:
            DocumentParser instance or None if not supported

        Raises:
            ValueError: If parser is not supported for this tier/type combination

        Testing Overrides:
            - FORCE_PARSER env var: Force specific parser for all requests
            - FORCE_USER_TIER env var: Force specific tier (overrides user_tier param)
        """
        # 1. Check for testing override: force specific parser
        if settings.force_parser:
            logger.warning(f"🧪 TESTING MODE: Forcing parser={settings.force_parser} (ignoring tier={user_tier}, pdf_type={pdf_type})")
            return cls._create_parser(settings.force_parser)

        # 2. Check for testing override: force specific tier
        if settings.force_user_tier:
            logger.warning(f"🧪 TESTING MODE: Forcing tier={settings.force_user_tier} (original tier was {user_tier})")
            user_tier = settings.force_user_tier

        # 3. Load parser configuration from settings
        parser_config = cls._load_parser_config()

        # 4. Get parser name from config
        parser_name = parser_config.get(user_tier, {}).get(pdf_type)

        if parser_name is None:
            logger.warning(f"Parser not supported for tier={user_tier}, pdf_type={pdf_type}")
            return None

        # 5. Create parser instance
        return cls._create_parser(parser_name)

    @classmethod
    def _create_parser(cls, parser_name: str) -> DocumentParser:
        """Create parser instance by name

        Args:
            parser_name: Parser identifier ('pymupdf', 'llmwhisperer', etc.)

        Returns:
            DocumentParser instance

        Raises:
            ValueError: If parser name is unknown
        """
        if parser_name == "pymupdf":
            return PyMuPDFParser()

        elif parser_name == "google_documentai" or parser_name == "documentai":
            return GoogleDocumentAIParser(
                project_id=None,      # Fallback to env
                location=None,        # Fallback to env
                processor_id=None,    # Fallback to env
                gcs_bucket=None,      # Fallback to env
                timeout_seconds=settings.document_ai_timeout_seconds
            )
        elif parser_name in ("azure_document_intelligence", "azure_doc_intelligence", "azure_docai"):
            return AzureDocumentIntelligenceParser(
                endpoint=settings.azure_doc_intelligence_endpoint or None,
                api_key=settings.azure_doc_intelligence_api_key or None,
                model_name=settings.azure_doc_model or None,
                timeout_seconds=settings.azure_doc_timeout_seconds or None,
            )

        else:
            raise ValueError(f"Unknown parser: {parser_name}")

    @classmethod
    def is_supported(cls, user_tier: str, pdf_type: str) -> bool:
        """Check if PDF type is supported for this user tier

        Args:
            user_tier: User tier ('free', 'pro', 'enterprise')
            pdf_type: PDF type ('digital' or 'scanned')

        Returns:
            True if supported, False otherwise
        """
        # If forcing a specific parser for testing, always return True
        if settings.force_parser:
            return True

        # Check testing override for tier
        if settings.force_user_tier:
            user_tier = settings.force_user_tier

        parser_config = cls._load_parser_config()
        parser_name = parser_config.get(user_tier, {}).get(pdf_type)
        return parser_name is not None

    @classmethod
    def get_upgrade_message(cls, user_tier: str, pdf_type: str) -> Optional[str]:
        """Get upgrade message if PDF type is not supported

        Args:
            user_tier: User tier
            pdf_type: PDF type

        Returns:
            Upgrade message or None if supported
        """
        if cls.is_supported(user_tier, pdf_type):
            return None

        if user_tier == "free" and pdf_type == "scanned":
            return (
                "Scanned PDFs require OCR processing, which is only available on Pro and Enterprise plans. "
                "Upgrade to Pro ($49/mo) to process scanned documents with high-quality OCR. "
                "Alternatively, convert your PDF to a digital format with extractable text."
            )

        return f"PDF type '{pdf_type}' is not supported for '{user_tier}' tier."
