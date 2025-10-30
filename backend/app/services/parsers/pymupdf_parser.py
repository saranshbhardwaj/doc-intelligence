# backend/app/services/parsers/pymupdf_parser.py
"""PyMuPDF (fitz) parser for digital PDFs - Free tier"""
import fitz  # PyMuPDF
import time
from typing import Optional
from .base import DocumentParser, ParserOutput
from app.utils.logging import logger


class PyMuPDFParser(DocumentParser):
    """Fast, free parser for digital PDFs using PyMuPDF

    Best for:
    - Digital PDFs with extractable text
    - Free tier users
    - Fast processing (no API calls)

    Does NOT support:
    - Scanned PDFs (images)
    - OCR
    """

    @property
    def name(self) -> str:
        return "pymupdf"

    @property
    def version(self) -> str:
        return fitz.version[0]  # PyMuPDF version

    @property
    def cost_per_page(self) -> float:
        return 0.0  # Free!

    def supports_pdf_type(self, pdf_type: str) -> bool:
        """PyMuPDF only supports digital PDFs"""
        return pdf_type == "digital"

    async def parse(self, file_path: str, pdf_type: str) -> ParserOutput:
        """Extract text from digital PDF using PyMuPDF

        Args:
            file_path: Path to PDF file
            pdf_type: Should be 'digital'

        Returns:
            ParserOutput with extracted text

        Raises:
            ValueError: If PDF is scanned (not enough text)
            Exception: If parsing fails
        """
        start_time = time.time()

        try:
            logger.info(f"PyMuPDF parsing: {file_path} (type: {pdf_type})")

            # Open PDF
            doc = fitz.open(file_path)
            page_count = len(doc)

            # Extract text from all pages
            text_parts = []
            for page_num in range(page_count):
                page = doc[page_num]
                page_text = page.get_text()
                text_parts.append(page_text)

            full_text = "\n\n".join(text_parts)
            doc.close()

            # Check if we got meaningful text
            if len(full_text.strip()) < 100:
                logger.warning(f"PyMuPDF extracted very little text ({len(full_text)} chars) - might be scanned PDF")
                raise ValueError(
                    "Could not extract sufficient text from PDF. "
                    "This appears to be a scanned PDF. "
                    "Please upgrade to Pro plan for OCR support."
                )

            processing_time_ms = int((time.time() - start_time) * 1000)

            logger.info(f"PyMuPDF extracted {len(full_text)} chars from {page_count} pages in {processing_time_ms}ms")

            return ParserOutput(
                text=full_text,
                page_count=page_count,
                parser_name=self.name,
                parser_version=self.version,
                processing_time_ms=processing_time_ms,
                cost_usd=0.0,
                pdf_type=pdf_type,
                metadata={
                    "char_count": len(full_text),
                    "avg_chars_per_page": len(full_text) / page_count if page_count > 0 else 0
                }
            )

        except ValueError:
            raise  # Re-raise ValueError for scanned PDFs
        except Exception as e:
            logger.exception(f"PyMuPDF parsing failed: {e}")
            raise Exception(f"Failed to parse PDF with PyMuPDF: {str(e)}")
