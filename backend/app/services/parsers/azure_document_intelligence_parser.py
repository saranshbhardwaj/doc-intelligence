"""Azure Document Intelligence parser implementation.

Extracts page-wise text and table content, merges them into a unified text output,
and returns standardized ParserOutput.

Pricing (per user request): $10 per 1000 pages (i.e., $0.01/page).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Dict

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

        # Edge case: Validate file_path
        if not file_path or not isinstance(file_path, str):
            raise ValueError(f"Invalid file_path: {file_path} (expected non-empty string)")

        # Edge case: Handle file open failures
        try:
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()
        except FileNotFoundError as e:
            raise RuntimeError(f"parse_error: PDF file not found at {file_path}") from e
        except PermissionError as e:
            raise RuntimeError(f"parse_error: Permission denied reading PDF file at {file_path}") from e
        except Exception as e:
            raise RuntimeError(f"parse_error: Failed to read PDF file at {file_path}: {e}") from e

        # Edge case: Validate PDF file is not empty
        if not pdf_bytes:
            raise ValueError(f"parse_error: PDF file at {file_path} is empty (0 bytes)")

        try:
            # Attempt calling SDK using new AnalyzeDocumentRequest signature.
            # Some releases of azure-ai-documentintelligence (including 1.0.0) expect a positional 'body'
            # and can mis-handle keyword usage, producing a TypeError about missing positional 'body'.
            analyze_request = AnalyzeDocumentRequest(bytes_source=pdf_bytes)
            poller = None
            try:
                # Prefer positional invocation to avoid signature mismatch issues.
                poller = self.client.begin_analyze_document(self.model_name, body=analyze_request)
            except TypeError as te:
                # Retry using raw bytes (older/alternate signature accepting the document directly)
                logger.warning(
                    "Azure begin_analyze_document signature mismatch; retrying with raw bytes",
                    extra={"error": str(te)}
                )
                try:
                    poller = self.client.begin_analyze_document(self.model_name, pdf_bytes)
                except Exception as e:
                    raise RuntimeError(f"parse_error: Azure begin_analyze_document failed after fallback: {e}") from e
            except AzureError as ae:
                raise RuntimeError(f"parse_error: Azure analyze call failed: {ae}") from ae
            except Exception as e:
                # Any unexpected failure during invocation – classify as parse_error
                raise RuntimeError(f"parse_error: Unexpected Azure analyze invocation failure: {e}") from e
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

            # Edge case: Validate result is not None
            if result is None:
                raise RuntimeError("parse_error: Azure API returned None result")

            # Extract structured data (paragraphs, sections, figures)
            structured_data = self._extract_structured_data(result)

            # Extract basic page data (text + tables)
            pages_data = self._extract_pages(result)

            # Edge case: Validate pages_data is not empty
            if not pages_data:
                raise ValueError("parse_error: Azure parser extracted no pages from PDF")

            # Build enhanced pages with paragraph roles and figures
            enhanced_pages = self._build_enhanced_pages(pages_data, structured_data)

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

            # Edge case: Validate page_count is positive
            if page_count <= 0:
                raise ValueError("parse_error: No pages extracted from PDF")

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
                # NEW: Enhanced structure for smart chunking
                "structured_data": {
                    "paragraphs": structured_data["paragraphs"],
                    "sections": structured_data["sections"],
                    "figures": structured_data["figures"],
                },
                # NEW: Enhanced pages with paragraph roles and figures
                "enhanced_pages": enhanced_pages,
                # NEW: Document-level structure summary
                "document_structure": {
                    "total_paragraphs": len(structured_data["paragraphs"]),
                    "total_sections": len(structured_data["sections"]),
                    "total_figures": len(structured_data["figures"]),
                    "paragraph_roles": self._count_paragraph_roles(structured_data["paragraphs"]),
                    "pages_with_headings": sum(1 for p in enhanced_pages if p["has_section_heading"]),
                    "pages_with_figures": sum(1 for p in enhanced_pages if p["has_figures"]),
                },
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
            # Prefix with parse_error so orchestrator can classify stage correctly & mark non-retryable.
            raise RuntimeError(f"parse_error: Unexpected failure in Azure parser: {e}") from e

    # --- Helpers ---
    def _extract_structured_data(self, result: AnalyzeResult) -> Dict:
        """Extract structured data (paragraphs, sections, figures) from Azure result.

        Returns a dict containing:
        - paragraphs: List of paragraphs with roles and metadata
        - sections: List of sections (hierarchical structure)
        - figures: List of figures with captions
        - content: Full document text (for span-based extraction)
        """
        structured_data = {
            "paragraphs": [],
            "sections": [],
            "figures": [],
            "content": getattr(result, "content", "")
        }

        # Extract paragraphs with roles
        logger.debug(f"Extracting paragraphs from Azure result")
        for para in getattr(result, "paragraphs", []) or []:
            if para is None:
                continue

            try:
                para_data = {
                    "content": getattr(para, "content", ""),
                    "role": getattr(para, "role", None),  # title, sectionHeading, pageHeader, etc.
                    "bounding_regions": [],
                    "spans": []
                }

                # Extract bounding regions
                for br in getattr(para, "bounding_regions", []) or []:
                    if br is None:
                        continue
                    para_data["bounding_regions"].append({
                        "page_number": getattr(br, "page_number", None),
                        "polygon": getattr(br, "polygon", [])
                    })

                # Extract spans (offset, length for content mapping)
                for span in getattr(para, "spans", []) or []:
                    if span is None:
                        continue
                    para_data["spans"].append({
                        "offset": getattr(span, "offset", 0),
                        "length": getattr(span, "length", 0)
                    })

                structured_data["paragraphs"].append(para_data)
            except Exception as e:
                logger.warning(f"Failed to extract paragraph: {e}")
                continue

        logger.info(f"Extracted {len(structured_data['paragraphs'])} paragraphs")

        # Extract sections (hierarchical grouping)
        logger.debug(f"Extracting sections from Azure result")
        for section in getattr(result, "sections", []) or []:
            if section is None:
                continue

            try:
                section_data = {
                    "spans": [],
                    "elements": getattr(section, "elements", []) or []
                }

                # Extract spans
                for span in getattr(section, "spans", []) or []:
                    if span is None:
                        continue
                    section_data["spans"].append({
                        "offset": getattr(span, "offset", 0),
                        "length": getattr(span, "length", 0)
                    })

                structured_data["sections"].append(section_data)
            except Exception as e:
                logger.warning(f"Failed to extract section: {e}")
                continue

        logger.info(f"Extracted {len(structured_data['sections'])} sections")

        # Extract figures with captions
        logger.debug(f"Extracting figures from Azure result")
        for figure in getattr(result, "figures", []) or []:
            if figure is None:
                continue

            try:
                figure_data = {
                    "id": getattr(figure, "id", None),
                    "bounding_regions": [],
                    "elements": getattr(figure, "elements", []) or [],
                    "caption": None
                }

                # Extract bounding regions
                for br in getattr(figure, "bounding_regions", []) or []:
                    if br is None:
                        continue
                    figure_data["bounding_regions"].append({
                        "page_number": getattr(br, "page_number", None),
                        "polygon": getattr(br, "polygon", [])
                    })

                # Extract caption if available
                caption = getattr(figure, "caption", None)
                if caption:
                    figure_data["caption"] = {
                        "content": getattr(caption, "content", ""),
                        "elements": getattr(caption, "elements", []) or []
                    }

                structured_data["figures"].append(figure_data)
            except Exception as e:
                logger.warning(f"Failed to extract figure: {e}")
                continue

        logger.info(f"Extracted {len(structured_data['figures'])} figures")

        return structured_data

    def _build_enhanced_pages(
        self,
        pages_data: List[_PageData],
        structured_data: Dict
    ) -> List[Dict]:
        """Build enhanced page structure with paragraphs, their roles, and figures.

        Args:
            pages_data: Basic page data from _extract_pages
            structured_data: Structured data from _extract_structured_data

        Returns:
            List of enhanced page dictionaries with rich metadata
        """
        enhanced_pages = []

        for page_data in pages_data:
            page_num = page_data.page_number

            # Find paragraphs on this page
            page_paragraphs = []
            for para in structured_data["paragraphs"]:
                for br in para["bounding_regions"]:
                    if br["page_number"] == page_num:
                        page_paragraphs.append(para)
                        break

            # Group paragraphs by role
            paragraphs_by_role = {}
            for para in page_paragraphs:
                role = para.get("role") or "content"
                paragraphs_by_role.setdefault(role, []).append(para)

            # Find figures on this page
            page_figures = []
            for figure in structured_data["figures"]:
                for br in figure["bounding_regions"]:
                    if br["page_number"] == page_num:
                        page_figures.append(figure)
                        break

            # Build enhanced page metadata
            enhanced_page = {
                "page_number": page_num,
                "text": page_data.text,
                "narrative_text": page_data.narrative_text,
                "char_count": page_data.char_count,

                # Rich structure
                "paragraphs": page_paragraphs,
                "paragraphs_by_role": paragraphs_by_role,
                "tables": page_data.table_data,
                "figures": page_figures,

                # Quick flags
                "has_title": "title" in paragraphs_by_role,
                "has_section_heading": "sectionHeading" in paragraphs_by_role,
                "has_page_header": "pageHeader" in paragraphs_by_role,
                "has_page_footer": "pageFooter" in paragraphs_by_role,
                "has_tables": page_data.table_count > 0,
                "has_figures": len(page_figures) > 0,

                # Extracted headings
                "section_headings": [
                    p["content"] for p in paragraphs_by_role.get("sectionHeading", [])
                ],
                "page_header_text": next(
                    (p["content"] for p in paragraphs_by_role.get("pageHeader", [])), None
                ),
                "page_footer_text": next(
                    (p["content"] for p in paragraphs_by_role.get("pageFooter", [])), None
                ),
            }

            enhanced_pages.append(enhanced_page)

        logger.info(
            f"Built enhanced page structure: "
            f"{len(enhanced_pages)} pages, "
            f"{sum(p['has_section_heading'] for p in enhanced_pages)} with headings, "
            f"{sum(p['has_figures'] for p in enhanced_pages)} with figures"
        )

        return enhanced_pages

    def _count_paragraph_roles(self, paragraphs: List[Dict]) -> Dict[str, int]:
        """Count paragraphs by role.

        Args:
            paragraphs: List of paragraph dicts with 'role' field

        Returns:
            Dict mapping role to count
        """
        role_counts = {}
        for para in paragraphs:
            role = para.get("role") or "content"
            role_counts[role] = role_counts.get(role, 0) + 1
        return role_counts

    def _extract_pages(self, result) -> List[_PageData]:
        """Extract page-wise text plus merged table content.

        Now also separates narrative text from tables for chunking strategies.
        """
        # Edge case: Validate result object
        if result is None:
            raise ValueError("result object is None")

        # Edge case: Validate result has pages
        if not hasattr(result, 'pages') or not result.pages:
            raise ValueError("Azure result has no pages")

        # Build initial page map with narrative text
        pages_narrative: dict[int, str] = {}
        for page in result.pages:
            # Edge case: Validate page object
            if page is None:
                logger.warning("Skipping None page in result.pages")
                continue

            # Edge case: Validate page_number exists
            if not hasattr(page, 'page_number'):
                logger.warning("Skipping page without page_number attribute")
                continue

            page_num = page.page_number

            # Edge case: Validate page_number is positive integer
            if not isinstance(page_num, int) or page_num <= 0:
                logger.warning(f"Skipping page with invalid page_number: {page_num}")
                continue

            lines = [line.content for line in getattr(page, "lines", []) or [] if line and hasattr(line, 'content')]
            pages_narrative[page_num] = "\n".join(lines)

        # Edge case: Validate pages_narrative is not empty after processing
        if not pages_narrative:
            raise ValueError("No valid pages found in Azure result")

        # Build table data by page
        tables_by_page: dict[int, List[Dict]] = {}
        for table in result.tables or []:
            # Edge case: Validate table object
            if table is None:
                logger.warning("Skipping None table in result.tables")
                continue

            if not table.bounding_regions:
                logger.warning("Skipping table without bounding_regions")
                continue

            # Edge case: Validate bounding_regions has at least one element
            if len(table.bounding_regions) == 0:
                logger.warning("Skipping table with empty bounding_regions")
                continue

            page_num = table.bounding_regions[0].page_number

            # Edge case: Validate page_num is valid
            if not isinstance(page_num, int) or page_num <= 0:
                logger.warning(f"Skipping table with invalid page_number: {page_num}")
                continue

            # Create matrix by iterating cells
            # Handle column_span for merged cells (common in financial table headers)
            cells_by_row: dict[int, dict[int, str]] = {}

            # Edge case: Validate table has cells
            if not hasattr(table, 'cells') or not table.cells:
                logger.warning(f"Skipping table on page {page_num} with no cells")
                continue

            for cell in table.cells:
                # Edge case: Validate cell object
                if cell is None:
                    continue

                # Edge case: Validate cell has required attributes
                if not hasattr(cell, 'row_index') or not hasattr(cell, 'column_index'):
                    logger.warning(f"Skipping cell without row_index or column_index on page {page_num}")
                    continue

                row_idx = cell.row_index
                col_idx = cell.column_index

                # Edge case: Validate indices are non-negative
                if row_idx < 0 or col_idx < 0:
                    logger.warning(f"Skipping cell with negative indices: row={row_idx}, col={col_idx}")
                    continue

                content = cell.content if hasattr(cell, 'content') else ""
                col_span = getattr(cell, "column_span", 1) or 1  # Default to 1 if not present

                # Edge case: Validate col_span is positive
                if not isinstance(col_span, int) or col_span <= 0:
                    col_span = 1

                # Place cell content at its starting column
                cells_by_row.setdefault(row_idx, {})[col_idx] = content

                # Fill subsequent columns for spanned cells (preserves alignment)
                # Example: "Amount %" with columnSpan=2 at column 1
                # → cells_by_row[0][1] = "Amount %", cells_by_row[0][2] = ""
                table_col_count = getattr(table, 'column_count', 0) or 0
                for span_offset in range(1, col_span):
                    if col_idx + span_offset < table_col_count:
                        cells_by_row[row_idx][col_idx + span_offset] = ""

            # Edge case: Skip table if no cells were processed
            if not cells_by_row:
                logger.warning(f"Skipping table on page {page_num} - no valid cells processed")
                continue

            # Reconstruct table as text (tab-separated format)
            table_text_lines = []
            table_col_count = getattr(table, 'column_count', 0) or 0

            # Edge case: Validate column_count is positive
            if table_col_count <= 0:
                # Infer from cells
                table_col_count = max((max(row.keys()) + 1 for row in cells_by_row.values() if row), default=0)
                if table_col_count <= 0:
                    logger.warning(f"Skipping table on page {page_num} - cannot determine column count")
                    continue

            for row_index in sorted(cells_by_row.keys()):
                row_cells = cells_by_row[row_index]
                columns = [row_cells.get(ci, "") for ci in range(table_col_count)]
                table_text_lines.append("\t".join(columns))

            table_row_count = getattr(table, 'row_count', 0) or len(cells_by_row)

            table_data = {
                "table_id": len(tables_by_page.get(page_num, [])),
                "text": "\n".join(table_text_lines),
                "row_count": table_row_count,
                "column_count": table_col_count,
            }

            tables_by_page.setdefault(page_num, []).append(table_data)

        # Build _PageData list with narrative and tables separated
        pages_data: List[_PageData] = []
        for page_num in sorted(pages_narrative.keys()):
            narrative = pages_narrative[page_num]
            page_tables = tables_by_page.get(page_num, [])

            # Edge case: Validate narrative is string
            if not isinstance(narrative, str):
                logger.warning(f"Skipping page {page_num} - narrative is not a string: {type(narrative).__name__}")
                continue

            # Build full text with tables embedded
            full_text = narrative
            for table_data in page_tables:
                # Edge case: Validate table_data structure
                if not isinstance(table_data, dict):
                    logger.warning(f"Skipping invalid table_data on page {page_num}")
                    continue

                table_text = table_data.get('text', '')
                if table_text:
                    full_text += f"\n\n[Table]\n{table_text}\n"

            # Edge case: Validate char_count is non-negative
            char_count = len(full_text.strip()) if full_text else 0
            if char_count < 0:
                char_count = 0

            pages_data.append(
                _PageData(
                    page_number=page_num,
                    text=full_text.strip(),
                    narrative_text=narrative.strip(),
                    table_data=page_tables,
                    table_count=len(page_tables),
                    char_count=char_count,
                )
            )

        # Edge case: Validate we have at least one valid page
        if not pages_data:
            raise ValueError("Failed to build any valid pages from Azure result")

        return pages_data
