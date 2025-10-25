# backend/app/document_processor.py
from io import BytesIO
from PyPDF2 import PdfReader
from typing import Tuple
from fastapi import HTTPException
from app.utils.logging import logger


class DocumentProcessor:
    """Handle PDF processing and text extraction"""
    
    def __init__(self, max_pages: int, max_file_size_bytes: int):
        self.max_pages = max_pages
        self.max_file_size_bytes = max_file_size_bytes
    
    def validate_file(self, filename: str, content: bytes):
        """
        Validate uploaded file.
        Raises HTTPException if validation fails.
        """
        # Check file extension
        if not filename.lower().endswith('.pdf'):
            logger.warning(f"Invalid file type: {filename}")
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported. Please upload a PDF document."
            )
        
        # Check file size
        size_mb = len(content) / (1024 * 1024)
        if len(content) > self.max_file_size_bytes:
            logger.warning(f"File too large: {size_mb:.1f}MB")
            raise HTTPException(
                status_code=400,
                detail=f"File too large ({size_mb:.1f}MB). Maximum size is {self.max_file_size_bytes / (1024*1024):.0f}MB."
            )
        
        logger.info(f"File validation passed: {filename} ({size_mb:.1f}MB)")
    
    def extract_text(self, content: bytes, filename: str) -> Tuple[str, int]:
        """
        Extract text from PDF content.
        Returns: (extracted_text, page_count)
        Raises HTTPException if extraction fails.
        """
        try:
            pdf_reader = PdfReader(BytesIO(content))
            page_count = len(pdf_reader.pages)
            
            logger.info(f"PDF loaded: {page_count} pages")
            
            # Check page limit
            if page_count > self.max_pages:
                logger.warning(f"Too many pages: {page_count}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Document has {page_count} pages. Demo is limited to {self.max_pages} pages. "
                           f"Contact us for processing larger documents."
                )
            
            # Extract text from all pages
            text_parts = []
            for i, page in enumerate(pdf_reader.pages, start=1):
                try:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
                    logger.debug(f"Extracted page {i}/{page_count}: {len(page_text)} chars")
                except Exception as e:
                    logger.warning(f"Error extracting page {i}: {e}")
                    text_parts.append("")  # Continue with empty text for this page
            
            full_text = "\n\n".join(text_parts)
            
            # Check if we got meaningful text
            if len(full_text.strip()) < 100:
                logger.error(f"Insufficient text extracted: {len(full_text)} chars")
                raise HTTPException(
                    status_code=400,
                    detail="Could not extract sufficient text from PDF. "
                           "This might be a scanned document or image-based PDF. "
                           "Please ensure it's a text-based PDF, or contact us for OCR support."
                )
            
            logger.info(f"Successfully extracted {len(full_text)} characters from {page_count} pages")
            return full_text, page_count
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"PDF processing failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process PDF: {str(e)}. "
                       f"The file might be corrupted or password-protected."
            )