# backend/app/services/parsers/llmwhisperer_parser.py
"""LLMWhisperer parser for scanned PDFs - Paid tier"""
import os
import time
import httpx
from typing import Optional
from io import BytesIO
from .base import DocumentParser, ParserOutput
from app.utils.logging import logger


class LLMWhispererParser(DocumentParser):
    """LLMWhisperer v2 parser for scanned and digital PDFs

    Best for:
    - Scanned PDFs (OCR required)
    - Pro/Enterprise tier users
    - LLM-optimized text extraction
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        mode: str = "high_quality",
        output_mode: str = "text",
        median_filter_size: int = 0,
        timeout_seconds: int = 300
    ):

        self.api_key = api_key or os.getenv("LLMWHISPERER_API_KEY", "")
        self.mode = mode
        self.output_mode = output_mode
        self.median_filter_size = median_filter_size
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://llmwhisperer-api.us-central.unstract.com/api/v2"

        # Pricing per page based on mode (v2 API pricing)
        self.pricing = {
            "native_text": 0.001,   # $1/1000 pages
            "low_cost": 0.005,      # $5/1000 pages
            "high_quality": 0.010,  # $10/1000 pages
            "form_elements": 0.015  # $15/1000 pages
        }

    @property
    def name(self) -> str:
        return "llmwhisperer"

    @property
    def version(self) -> str:
        return "v2"

    @property
    def cost_per_page(self) -> float:
        return self.pricing.get(self.mode, 0.010)

    def supports_pdf_type(self, pdf_type: str) -> bool:
        """LLMWhisperer supports both digital and scanned PDFs"""
        return pdf_type in ["digital", "scanned"]

    async def parse(self, file_path: str, pdf_type: str) -> ParserOutput:
        """Extract text from PDF using LLMWhisperer v2 API (async workflow)

        Args:
            file_path: Path to PDF file
            pdf_type: 'digital' or 'scanned'

        Returns:
            ParserOutput with extracted text

        Raises:
            Exception: If API call fails or no API key
        """
        if not self.api_key:
            raise Exception("LLMWhisperer API key not configured. Set LLMWHISPERER_API_KEY environment variable.")

        start_time = time.time()

        try:
            logger.info(f"LLMWhisperer v2 parsing: {file_path} (type: {pdf_type}, mode: {self.mode})")

            # Read the PDF file into memory
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()

            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                # Step 1: Submit document for processing
                logger.info(f"LLMWhisperer: Submitting document for processing...")

                # Prepare query parameters
                params = {
                    "mode": self.mode,
                    "output_mode": self.output_mode,
                }

                # Add median filter for noise removal (only works with low_cost mode)
                if self.mode == "low_cost" and self.median_filter_size > 0:
                    params["median_filter_size"] = self.median_filter_size
                    logger.info(f"LLMWhisperer: Using median_filter_size={self.median_filter_size} for noise removal")

                # Use binary upload (--data-binary equivalent) as per official API docs
                submit_response = await client.post(
                    f"{self.base_url}/whisper",
                    headers={
                        "unstract-key": self.api_key,
                        "Content-Type": "application/pdf",
                    },
                    params=params,
                    content=pdf_bytes
                )

                if submit_response.status_code not in [200, 202]:
                    error_msg = f"LLMWhisperer submit error: {submit_response.status_code} - {submit_response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

                submit_result = submit_response.json()
                whisper_hash = submit_result.get("whisper_hash") or submit_result.get("whisper-hash")

                if not whisper_hash:
                    raise Exception(f"No whisper_hash in response: {submit_result}")

                logger.info(f"LLMWhisperer: Document submitted, whisper_hash={whisper_hash}")

                # Step 2: Poll for completion
                max_polls = 60  # Poll for up to 5 minutes (60 * 5 seconds)
                poll_interval = 5  # seconds

                for poll_count in range(max_polls):
                    status_response = await client.get(
                        f"{self.base_url}/whisper-status",
                        headers={
                            "unstract-key": self.api_key,
                        },
                        params={
                            "whisper_hash": whisper_hash
                        }
                    )

                    if status_response.status_code != 200:
                        error_msg = f"LLMWhisperer status error: {status_response.status_code} - {status_response.text}"
                        logger.error(error_msg)
                        raise Exception(error_msg)

                    status_result = status_response.json()
                    status = status_result.get("status")

                    logger.info(f"LLMWhisperer: Poll {poll_count + 1}/{max_polls}, status={status}")

                    if status == "processed":
                        break
                    elif status in ["failed", "error"]:
                        raise Exception(f"LLMWhisperer processing failed: {status_result}")

                    # Wait before next poll
                    if poll_count < max_polls - 1:
                        time.sleep(poll_interval)
                else:
                    raise Exception(f"LLMWhisperer processing timed out after {max_polls * poll_interval} seconds")

                # Step 3: Retrieve results
                logger.info(f"LLMWhisperer: Retrieving extracted text...")
                retrieve_response = await client.get(
                    f"{self.base_url}/whisper-retrieve",
                    headers={
                        "unstract-key": self.api_key,
                    },
                    params={
                        "whisper_hash": whisper_hash
                    }
                )

                if retrieve_response.status_code != 200:
                    error_msg = f"LLMWhisperer retrieve error: {retrieve_response.status_code} - {retrieve_response.text}"
                    logger.error(error_msg)
                    raise Exception(error_msg)

                retrieve_result = retrieve_response.json()

            # Extract text and metadata from response
            # v2 API returns text in "result_text" field (when text_only=false, which is default)
            extracted_text = retrieve_result.get("result_text", "") or retrieve_result.get("extracted_text", "")

            # Get page count from detail endpoint if available, otherwise estimate
            page_count = retrieve_result.get("page_count", 0)
            if page_count == 0:
                # Estimate from page separator count
                page_separator = retrieve_result.get("page_seperator", "<<<")
                page_count = extracted_text.count(page_separator) + 1 if page_separator else 1

            processing_time_ms = int((time.time() - start_time) * 1000)
            cost = page_count * self.cost_per_page

            logger.info(f"LLMWhisperer extracted {len(extracted_text)} chars from {page_count} pages in {processing_time_ms}ms (cost: ${cost:.4f})")

            return ParserOutput(
                text=extracted_text,
                page_count=page_count,
                parser_name=self.name,
                parser_version=self.version,
                processing_time_ms=processing_time_ms,
                cost_usd=cost,
                pdf_type=pdf_type,
                metadata={
                    "char_count": len(extracted_text),
                    "mode": self.mode,
                    "whisper_hash": whisper_hash,
                    "avg_chars_per_page": len(extracted_text) / page_count if page_count > 0 else 0
                }
            )

        except Exception as e:
            logger.exception(f"LLMWhisperer v2 parsing failed: {e}")
            raise Exception(f"Failed to parse PDF with LLMWhisperer v2: {str(e)}")
