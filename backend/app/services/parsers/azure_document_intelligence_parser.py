"""Azure Document Intelligence parser implementation.

Extracts page-wise text and table content, merges them into a unified text output,
and returns standardized ParserOutput.

Pricing (per user request): $10 per 1000 pages (i.e., $0.01/page).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError

from app.services.parsers.base import DocumentParser, ParserOutput
from app.config import settings
from app.utils.logging import logger


@dataclass
class _PageData:
    page_number: int
    text: str  # Full text with tables embedded
    table_count: int
    char_count: int
    narrative_text: str = ""  # Text without tables (for chunking)
    table_data: List[Dict] = None  # Separate table data (for chunking)

    def __post_init__(self):
        if self.table_data is None:
            self.table_data = []


class AzureDocumentIntelligenceParser(DocumentParser):
    """Parser using Azure Document Intelligence prebuilt models.

    Uses the prebuilt-layout model for layout, lines, and tables.

    Notes:
        - Supports both digital and scanned PDFs (Azure handles OCR automatically).
        - Merges table data into page text with a simple tab-separated format.
        - Assigns cost based on $0.01 per page.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        endpoint = endpoint or settings.azure_doc_intelligence_endpoint
        api_key = api_key or settings.azure_doc_intelligence_api_key
        model_name = model_name or settings.azure_doc_model
        timeout_seconds = timeout_seconds or settings.azure_doc_timeout_seconds

        if not endpoint:
            raise ValueError("AZURE_DOC_INTELLIGENCE_ENDPOINT is required")
        if not api_key:
            raise ValueError("AZURE_DOC_INTELLIGENCE_API_KEY is required")

        self.endpoint = endpoint
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self._cost_per_page = 0.01  # $10 per 1000 pages

        try:
            self.client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(api_key))
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Azure DocumentIntelligenceClient: {e}")

        logger.info(
            f"AzureDocumentIntelligenceParser initialized: model={self.model_name}, timeout={self.timeout_seconds}s"
        )

    # --- Required abstract property implementations ---
    @property
    def name(self) -> str:  # type: ignore[override]
        return "azure_document_intelligence"

    @property
    def version(self) -> str:  # type: ignore[override]
        # Azure SDK doesn't expose model version easily; allow manual tracking.
        return "1.0.0"

    @property
    def cost_per_page(self) -> float:  # type: ignore[override]
        return self._cost_per_page

    def supports_pdf_type(self, pdf_type: str) -> bool:  # type: ignore[override]
        # Azure handles both digital & scanned via OCR.
        return pdf_type in ("digital", "scanned")

    # --- Core parse method ---
    async def parse(self, file_path: str, pdf_type: str) -> ParserOutput:  # type: ignore[override]
        start_time = time.time()
        logger.info(
            f"AzureDocumentIntelligenceParser: parsing file={file_path} pdf_type={pdf_type} model={self.model_name}"
        )

        try:
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()
                # New SDK requires AnalyzeDocumentRequest with bytes_source
                analyze_request = AnalyzeDocumentRequest(bytes_source=pdf_bytes)
                poller = self.client.begin_analyze_document(
                    model_id=self.model_name,
                    analyze_request=analyze_request
                )
                try:
                    # Apply explicit timeout; Azure SDK raises TimeoutError on wait expiry
                    result: AnalyzeResult = poller.result(timeout=self.timeout_seconds)
                except TimeoutError as te:
                    processing_time_ms = int((time.time() - start_time) * 1000)
                    logger.error(
                        f"Azure Document Intelligence timeout after {self.timeout_seconds}s (elapsed {processing_time_ms}ms)",
                        extra={"timeout_seconds": self.timeout_seconds},
                    )
                    raise RuntimeError(
                        f"Azure Document Intelligence processing exceeded timeout of {self.timeout_seconds}s"
                    ) from te

            pages_data = self._extract_pages(result)

            # Combine page texts
            full_text = "\n\n".join(p.text for p in pages_data)

            # Basic quality check similar to other parsers
            if len(full_text.strip()) < 100:
                logger.warning(
                    f"Azure parser extracted very little text ({len(full_text)} chars) - may be low-quality scan"
                )
                raise ValueError(
                    "Could not extract sufficient text from PDF. This appears to be a low-text or image-heavy document."
                )

            processing_time_ms = int((time.time() - start_time) * 1000)
            page_count = len(pages_data)
            cost = page_count * self.cost_per_page

            logger.info(
                f"Azure parser extracted {len(full_text)} chars from {page_count} pages in {processing_time_ms}ms (cost=${cost:.2f})"
            )

            # Build tables summary if available
            tables_meta = []
            try:
                for table in getattr(result, "tables", []) or []:
                    page_num = table.bounding_regions[0].page_number if table.bounding_regions else None
                    tables_meta.append({
                        "page_number": page_num,
                        "row_count": getattr(table, "row_count", None),
                        "column_count": getattr(table, "column_count", None),
                        "cell_count": len(getattr(table, "cells", []) or []),
                    })
            except Exception:
                pass

            metadata = {
                "model_name": self.model_name,
                "char_count": len(full_text),
                "avg_chars_per_page": len(full_text) / page_count if page_count else 0,
                "pages": [
                    {
                        "page_number": p.page_number,
                        "char_count": p.char_count,
                        "table_count": p.table_count,
                    }
                    for p in pages_data
                ],
                "tables": tables_meta,
                "total_tables": len(tables_meta),
                # Store per-page data for chunking (includes text, narrative, and tables)
                "pages_data": [
                    {
                        "page_number": p.page_number,
                        "text": p.text,  # Full page text with tables
                        "narrative_text": p.narrative_text,  # Text without tables
                        "tables": p.table_data,  # Separate table data
                        "table_count": p.table_count,
                        "char_count": p.char_count,
                    }
                    for p in pages_data
                ],
            }

            return ParserOutput(
                text=full_text,
                page_count=page_count,
                parser_name=self.name,
                parser_version=self.version,
                processing_time_ms=processing_time_ms,
                cost_usd=cost,
                pdf_type=pdf_type,
                metadata=metadata,
            )

        except ValueError:
            # Propagate intentional low-text error
            raise
        except AzureError as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Azure Document Intelligence API error after {processing_time_ms}ms: {e}",
                extra={"error_type": type(e).__name__},
            )
            raise RuntimeError(f"Azure Document Intelligence parsing failed: {e}") from e
        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.exception(
                f"Unexpected Azure parser failure after {processing_time_ms}ms: {e}",
            )
            raise RuntimeError(f"Unexpected failure in Azure parser: {e}") from e

    # --- Helpers ---
    def _extract_pages(self, result) -> List[_PageData]:
        """Extract page-wise text plus merged table content.

        Now also separates narrative text from tables for chunking strategies.
        """
        # Build initial page map with narrative text
        pages_narrative: dict[int, str] = {}
        for page in result.pages:
            lines = [line.content for line in getattr(page, "lines", []) or []]
            pages_narrative[page.page_number] = "\n".join(lines)

        # Build table data by page
        tables_by_page: dict[int, List[Dict]] = {}
        for table in result.tables or []:
            if not table.bounding_regions:
                continue
            page_num = table.bounding_regions[0].page_number

            # Create matrix by iterating cells
            # Handle column_span for merged cells (common in financial table headers)
            cells_by_row: dict[int, dict[int, str]] = {}
            for cell in table.cells:
                row_idx = cell.row_index
                col_idx = cell.column_index
                content = cell.content
                col_span = getattr(cell, "column_span", 1) or 1  # Default to 1 if not present

                # Place cell content at its starting column
                cells_by_row.setdefault(row_idx, {})[col_idx] = content

                # Fill subsequent columns for spanned cells (preserves alignment)
                # Example: "Amount %" with columnSpan=2 at column 1
                # → cells_by_row[0][1] = "Amount %", cells_by_row[0][2] = ""
                for span_offset in range(1, col_span):
                    if col_idx + span_offset < table.column_count:
                        cells_by_row[row_idx][col_idx + span_offset] = ""

            # Reconstruct table as text (tab-separated format)
            table_text_lines = []
            for row_index in sorted(cells_by_row.keys()):
                row_cells = cells_by_row[row_index]
                columns = [row_cells.get(ci, "") for ci in range(table.column_count)]
                table_text_lines.append("\t".join(columns))

            table_data = {
                "table_id": len(tables_by_page.get(page_num, [])),
                "text": "\n".join(table_text_lines),
                "row_count": table.row_count,
                "column_count": table.column_count,
            }

            tables_by_page.setdefault(page_num, []).append(table_data)

        # Build _PageData list with narrative and tables separated
        pages_data: List[_PageData] = []
        for page_num in sorted(pages_narrative.keys()):
            narrative = pages_narrative[page_num]
            page_tables = tables_by_page.get(page_num, [])

            # Build full text with tables embedded
            full_text = narrative
            for table_data in page_tables:
                full_text += f"\n\n[Table]\n{table_data['text']}\n"

            pages_data.append(
                _PageData(
                    page_number=page_num,
                    text=full_text.strip(),
                    narrative_text=narrative.strip(),
                    table_data=page_tables,
                    table_count=len(page_tables),
                    char_count=len(full_text.strip()),
                )
            )
        return pages_data
