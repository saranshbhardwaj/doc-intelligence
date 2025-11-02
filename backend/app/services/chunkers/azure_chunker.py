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

        if not pages_data:
            raise ValueError(
                "Azure parser output missing 'pages_data' in metadata. "
                "Ensure you're using an updated AzureDocumentIntelligenceParser."
            )

        # Build chunks
        chunks: List[Chunk] = []

        for page_data in pages_data:
            page_num = page_data["page_number"]
            full_text = page_data["text"]
            narrative_text = page_data.get("narrative_text", "")
            tables = page_data.get("tables", [])
            table_count = page_data.get("table_count", 0)
            char_count = page_data.get("char_count", len(full_text))

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

        logger.info(f"Created {len(chunks)} page-wise chunks "
                   f"({sum(1 for c in chunks if c.metadata['has_tables'])} with tables)")

        return ChunkingOutput(
            chunks=chunks,
            strategy=ChunkStrategy.PAGE_WISE,
            metadata={
                "source_parser": parser_output.parser_name,
                "total_pages": parser_output.page_count,
                "total_chars": sum(c.char_count for c in chunks),
                "narrative_chars": sum(c.narrative_char_count for c in chunks),
                "pages_with_tables": sum(1 for c in chunks if c.metadata["has_tables"]),
                "total_tables": sum(c.metadata["table_count"] for c in chunks),
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
