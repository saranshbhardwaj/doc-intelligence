# backend/app/services/parsers/base.py
"""Base class for all document parsers"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class ParserType(str, Enum):
    """Available parser types"""
    PYMUPDF = "pymupdf"
    LLMWHISPERER = "llmwhisperer"
    TEXTRACT = "textract"
    GOOGLE_LAYOUT = "google_layout"
    AZURE_DOCUMENT_INTELLIGENCE = "azure_document_intelligence"


@dataclass
class ParserOutput:
    """Output from document parser"""
    text: str
    page_count: int
    parser_name: str
    parser_version: Optional[str] = None
    processing_time_ms: int = 0
    cost_usd: float = 0.0
    pdf_type: Optional[str] = None  # 'digital' or 'scanned'
    metadata: Optional[dict] = None  # Any additional parser-specific metadata


class DocumentParser(ABC):
    """Base class for all document parsers

    Each parser implementation should:
    1. Extract text from PDF (digital or scanned)
    2. Track processing time and cost
    3. Return standardized ParserOutput
    """

    @abstractmethod
    async def parse(self, file_path: str, pdf_type: str) -> ParserOutput:
        """Parse document and return extracted text

        Args:
            file_path: Path to PDF file
            pdf_type: 'digital' or 'scanned'

        Returns:
            ParserOutput with extracted text and metadata

        Raises:
            Exception if parsing fails
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Parser identifier (e.g., 'pymupdf', 'llmwhisperer')"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Parser version"""
        pass

    @property
    @abstractmethod
    def cost_per_page(self) -> float:
        """Cost per page in USD"""
        pass

    @abstractmethod
    def supports_pdf_type(self, pdf_type: str) -> bool:
        """Check if parser supports this PDF type

        Args:
            pdf_type: 'digital' or 'scanned'

        Returns:
            True if parser can handle this PDF type
        """
        pass
