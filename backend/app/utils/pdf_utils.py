# backend/app/utils/pdf_utils.py
"""PDF utility functions"""
import fitz  # PyMuPDF
from app.utils.logging import logger


def detect_pdf_type(pdf_path: str, sample_pages: int = 3, threshold: int = 100) -> str:
    """Detect if PDF is digital (has text) or scanned (images only)

    Args:
        pdf_path: Path to PDF file
        sample_pages: Number of pages to sample (default: first 3)
        threshold: Minimum average chars per page to consider digital (default: 100)

    Returns:
        'digital' if PDF has extractable text, 'scanned' if it appears to be images

    Examples:
        >>> detect_pdf_type("document.pdf")
        'digital'
        >>> detect_pdf_type("scanned_doc.pdf")
        'scanned'
    """
    try:
        doc = fitz.open(pdf_path)
        total_chars = 0
        pages_to_check = min(sample_pages, len(doc))

        # Sample first few pages for speed
        for page_num in range(pages_to_check):
            page = doc[page_num]
            text = page.get_text()
            total_chars += len(text.strip())

        doc.close()

        # Calculate average characters per page
        avg_chars_per_page = total_chars / pages_to_check if pages_to_check > 0 else 0

        # Determine PDF type based on threshold
        pdf_type = "digital" if avg_chars_per_page >= threshold else "scanned"

        logger.info(f"PDF type detection: {pdf_type} (avg chars/page: {avg_chars_per_page:.0f}, threshold: {threshold})")

        return pdf_type

    except Exception as e:
        logger.warning(f"Error detecting PDF type: {e}. Defaulting to 'digital'")
        return "digital"  # Default to digital on error
