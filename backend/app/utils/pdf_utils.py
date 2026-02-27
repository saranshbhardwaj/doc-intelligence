# backend/app/utils/pdf_utils.py
"""PDF utility functions"""
import PyPDF2
from app.utils.logging import logger


def detect_pdf_type(pdf_path: str, sample_pages: int = 3, threshold: int = 100) -> str:
    """Detect if PDF is digital (has text) or scanned (images only).

    Used for metadata/logging only — Azure Document Intelligence handles both types natively.

    Args:
        pdf_path: Path to PDF file
        sample_pages: Number of pages to sample (default: first 3)
        threshold: Minimum average chars per page to consider digital (default: 100)

    Returns:
        'digital' if PDF has extractable text, 'scanned' if it appears to be images
    """
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            total_chars = 0
            pages_to_check = min(sample_pages, len(reader.pages))

            for page_num in range(pages_to_check):
                text = reader.pages[page_num].extract_text() or ""
                total_chars += len(text.strip())

        avg_chars_per_page = total_chars / pages_to_check if pages_to_check > 0 else 0
        pdf_type = "digital" if avg_chars_per_page >= threshold else "scanned"

        logger.info(f"PDF type detection: {pdf_type} (avg chars/page: {avg_chars_per_page:.0f}, threshold: {threshold})")
        return pdf_type

    except Exception as e:
        logger.warning(f"Error detecting PDF type: {e}. Defaulting to 'digital'")
        return "digital"
