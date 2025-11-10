"""Azure Document Intelligence specific chunker.

Implements page-wise chunking strategy for Azure parser output.
Separates narrative text from tables for flexible LLM processing.
"""
from typing import List

from app.services.chunkers.base import (
    DocumentChunker,
    Chunk,
    ChunkingOutput,
    ChunkStrategy,
)
from app.services.parsers.base import ParserOutput
from app.utils.logging import logger


class AzurePageWiseChunker(DocumentChunker):
    """Page-wise chunker for Azure Document Intelligence parser output.

    Strategy:
    - One chunk per page
    - Tables kept intact (not split)
    - Narrative text separated from tables for flexible processing
    - Raw table data preserved for expensive LLM

    This is the baseline chunking strategy. Future enhancements:
    - Semantic chunking for very long pages
    - Section-based chunking if headers detected
    """

    def chunk(self, parser_output: ParserOutput) -> ChunkingOutput:
        """Chunk Azure parser output into page-wise chunks.

        Args:
            parser_output: Output from AzureDocumentIntelligenceParser

        Returns:
            ChunkingOutput with page-wise chunks

        Raises:
            ValueError if parser_output doesn't have Azure metadata
        """
        logger.info(f"Chunking {parser_output.page_count} pages using page-wise strategy")

        # Extract pages_data from metadata
        metadata = parser_output.metadata or {}
        pages_data = metadata.get("pages_data")

        # Edge case: Validate pages_data exists and is not empty
        if not pages_data:
            raise ValueError(
                "Azure parser output missing 'pages_data' in metadata. "
                "Ensure you're using an updated AzureDocumentIntelligenceParser."
            )

        if not isinstance(pages_data, list):
            raise ValueError(f"Expected pages_data to be a list, got {type(pages_data).__name__}")

        if len(pages_data) == 0:
            raise ValueError("pages_data is empty - no pages to chunk")

        # Build chunks
        chunks: List[Chunk] = []

        for idx, page_data in enumerate(pages_data):
            # Edge case: Validate page_data structure
            if not isinstance(page_data, dict):
                logger.warning(
                    f"Skipping invalid page_data at index {idx}: expected dict, got {type(page_data).__name__}"
                )
                continue

            # Edge case: Validate required fields
            if "page_number" not in page_data:
                logger.warning(f"Skipping page_data at index {idx}: missing 'page_number'")
                continue

            if "text" not in page_data:
                logger.warning(f"Skipping page_data at index {idx}: missing 'text'")
                continue

            page_num = page_data["page_number"]

            # Edge case: Validate page number is positive
            if not isinstance(page_num, int) or page_num <= 0:
                logger.warning(
                    f"Skipping page_data with invalid page_number: {page_num} (expected positive integer)"
                )
                continue

            full_text = page_data["text"]
            narrative_text = page_data.get("narrative_text", "")
            tables = page_data.get("tables", [])
            table_count = page_data.get("table_count", 0)
            char_count = page_data.get("char_count", len(full_text) if full_text else 0)

            # Edge case: Validate char_count is non-negative
            if char_count < 0:
                logger.warning(f"Page {page_num} has negative char_count {char_count}, using 0")
                char_count = 0

            chunk = Chunk(
                chunk_id=f"page_{page_num}",
                text=full_text,  # Full text with tables (for complete context)
                narrative_text=narrative_text,  # Text without tables (for summarization)
                tables=tables,  # Separate table data (preserve for expensive LLM)
                metadata={
                    "page_number": page_num,
                    "char_count": char_count,
                    "narrative_char_count": len(narrative_text),
                    "table_count": table_count,
                    "has_tables": table_count > 0,
                    "chunk_type": "page",
                    "source_parser": parser_output.parser_name,
                }
            )

            chunks.append(chunk)

        # Edge case: Ensure we created at least one valid chunk
        if not chunks:
            raise ValueError(
                "No valid chunks created after processing pages_data. "
                "All pages may have failed validation."
            )

        logger.info(f"Created {len(chunks)} page-wise chunks "
                   f"({sum(1 for c in chunks if c.metadata.get('has_tables', False))} with tables)")

        # Edge case: Safely compute metadata sums with defaults
        try:
            total_chars = sum(c.char_count for c in chunks)
            narrative_chars = sum(c.narrative_char_count for c in chunks)
            pages_with_tables = sum(1 for c in chunks if c.metadata.get("has_tables", False))
            total_tables = sum(c.metadata.get("table_count", 0) for c in chunks)
        except (AttributeError, TypeError) as e:
            logger.warning(f"Error computing chunk metadata sums: {e}", exc_info=True)
            total_chars = 0
            narrative_chars = 0
            pages_with_tables = 0
            total_tables = 0

        return ChunkingOutput(
            chunks=chunks,
            strategy=ChunkStrategy.PAGE_WISE,
            metadata={
                "source_parser": parser_output.parser_name,
                "total_pages": parser_output.page_count,
                "total_chars": total_chars,
                "narrative_chars": narrative_chars,
                "pages_with_tables": pages_with_tables,
                "total_tables": total_tables,
            }
        )

    @property
    def name(self) -> str:
        return "azure_page_wise"

    @property
    def strategy(self) -> ChunkStrategy:
        return ChunkStrategy.PAGE_WISE

    def supports_parser(self, parser_name: str) -> bool:
        """This chunker supports Azure Document Intelligence parser."""
        return parser_name == "azure_document_intelligence"
