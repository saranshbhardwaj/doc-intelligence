"""Multi-stage document extraction pipeline.

Orchestrates the flow: Parse → Chunk → Summarize (cheap LLM) → Extract (expensive LLM)

This service encapsulates all the business logic for processing documents through the
chunking pipeline, keeping the API endpoint handlers thin and focused on HTTP concerns.
"""
from dataclasses import dataclass
from typing import Optional

from app.services.parsers.base import ParserOutput
from app.services.chunkers import ChunkerFactory
from app.services.llm_client import LLMClient
from app.config import settings
from app.utils.logging import logger
from app.utils.file_utils import save_chunks, save_summaries, save_combined_context


@dataclass
class PipelineResult:
    """Result from the extraction pipeline.

    Attributes:
        extracted_data: The structured JSON from the expensive LLM
        used_chunking: Whether chunking was used (vs direct LLM call)
        metadata: Pipeline execution metadata (compression ratio, chunk counts, etc.)
    """
    extracted_data: dict
    used_chunking: bool
    metadata: dict


class ExtractionPipeline:
    """Handles multi-stage LLM processing with optional chunking.

    This service orchestrates the extraction pipeline:
    1. Check if chunking is supported for the parser
    2. If yes: chunk → summarize with cheap LLM → combine → extract with expensive LLM
    3. If no: direct extraction with expensive LLM

    Usage:
        pipeline = ExtractionPipeline(llm_client)
        result = await pipeline.process(parser_output, request_id, filename)
    """

    def __init__(self, llm_client: LLMClient):
        """Initialize the pipeline.

        Args:
            llm_client: LLM client for both cheap and expensive model calls
        """
        self.llm_client = llm_client

    async def process(
        self,
        parser_output: ParserOutput,
        request_id: str,
        filename: str
    ) -> PipelineResult:
        """Run the extraction pipeline on parser output.

        Args:
            parser_output: Output from document parser (Azure, Google, etc.)
            request_id: Unique request ID for logging/tracking
            filename: Original filename for logging

        Returns:
            PipelineResult with extracted data and metadata

        Raises:
            Exception: If extraction fails (propagated from LLM client)
        """
        # Check if chunking is supported and enabled
        if settings.enable_chunking and ChunkerFactory.supports_chunking(parser_output.parser_name):
            logger.info("Using chunked extraction pipeline", extra={"request_id": request_id})
            return await self._process_with_chunking(parser_output, request_id, filename)
        else:
            logger.info(
                f"Using direct extraction pipeline (chunking {'disabled' if not settings.enable_chunking else 'not supported'})",
                extra={"request_id": request_id, "parser": parser_output.parser_name}
            )
            return await self._process_direct(parser_output, request_id, filename)

    async def _process_with_chunking(
        self,
        parser_output: ParserOutput,
        request_id: str,
        filename: str
    ) -> PipelineResult:
        """Process using multi-stage chunking pipeline.

        Pipeline:
        1. Chunk the document (page-wise, semantic, etc.)
        2. Summarize narrative chunks with cheap LLM (Haiku)
        3. Combine summaries + raw tables
        4. Extract structured data with expensive LLM (Sonnet)

        Args:
            parser_output: Parsed document
            request_id: Request ID for logging
            filename: Original filename

        Returns:
            PipelineResult with extracted data and metadata
        """
        # Step 1: Chunk the document
        chunker = ChunkerFactory.get_chunker(parser_output.parser_name)
        chunking_output = chunker.chunk(parser_output)

        logger.info(
            f"Created {chunking_output.total_chunks} chunks "
            f"({chunking_output.chunks_with_tables} with tables, "
            f"{len(chunking_output.get_narrative_chunks())} narrative-only)",
            extra={"request_id": request_id}
        )

        # Save chunks for debugging
        save_chunks(
            request_id,
            {
                "strategy": chunking_output.strategy.value,
                "total_chunks": chunking_output.total_chunks,
                "metadata": chunking_output.metadata,
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "text": c.text[:500],  # First 500 chars preview
                        "metadata": c.metadata
                    }
                    for c in chunking_output.chunks
                ]
            },
            filename
        )

        # Step 2: Summarize narrative chunks with cheap LLM
        narrative_chunks = chunking_output.get_narrative_chunks()
        narrative_summaries = []

        if narrative_chunks:
            narrative_summaries = await self._summarize_narrative_chunks(
                narrative_chunks,
                request_id
            )

            # Save summaries for quality verification
            save_summaries(
                request_id,
                {
                    "model": settings.cheap_llm_model,
                    "total_summaries": len(narrative_summaries),
                    "batch_size": settings.chunk_batch_size,
                    "summaries": [
                        {
                            "page": narrative_chunks[i].metadata["page_number"],
                            "original_chars": narrative_chunks[i].narrative_char_count,
                            "summary": summary
                        }
                        for i, summary in enumerate(narrative_summaries)
                    ]
                },
                filename
            )

        # Step 3: Combine summaries and tables
        combined_context, context_metadata = self._build_combined_context(
            narrative_chunks,
            narrative_summaries,
            chunking_output.get_table_chunks(),
            chunking_output.total_chars
        )

        logger.info(
            f"Combined context: {len(combined_context)} chars "
            f"(compressed from {chunking_output.total_chars} chars)",
            extra={
                "request_id": request_id,
                "compression_ratio": context_metadata["compression_ratio"]
            }
        )

        # Save combined context
        save_combined_context(request_id, combined_context, context_metadata, filename)

        # Step 4: Extract with expensive LLM
        logger.info("Calling expensive LLM (Sonnet) with chunked context", extra={"request_id": request_id})
        extracted_data = self.llm_client.extract_structured_data(combined_context)

        return PipelineResult(
            extracted_data=extracted_data,
            used_chunking=True,
            metadata={
                "chunking_strategy": chunking_output.strategy.value,
                "total_chunks": chunking_output.total_chunks,
                "chunks_with_tables": chunking_output.chunks_with_tables,
                "narrative_chunks": len(narrative_chunks),
                "compression_ratio": context_metadata["compression_ratio"],
                "original_chars": chunking_output.total_chars,
                "compressed_chars": len(combined_context),
            }
        )

    async def _process_direct(
        self,
        parser_output: ParserOutput,
        request_id: str,
        filename: str
    ) -> PipelineResult:
        """Process without chunking - direct LLM extraction.

        Used when:
        - Chunking is disabled
        - Parser doesn't support chunking
        - Document is too small to benefit from chunking

        Args:
            parser_output: Parsed document
            request_id: Request ID for logging
            filename: Original filename

        Returns:
            PipelineResult with extracted data
        """
        logger.info("Calling LLM for direct extraction", extra={"request_id": request_id})
        extracted_data = self.llm_client.extract_structured_data(parser_output.text)

        return PipelineResult(
            extracted_data=extracted_data,
            used_chunking=False,
            metadata={
                "chunking_strategy": "none",
                "total_chars": len(parser_output.text),
            }
        )

    async def _summarize_narrative_chunks(
        self,
        narrative_chunks: list,
        request_id: str
    ) -> list[str]:
        """Summarize narrative chunks using cheap LLM with batch processing.

        Processes chunks in batches (default 10) to optimize API calls.

        Args:
            narrative_chunks: List of Chunk objects containing narrative text
            request_id: Request ID for logging

        Returns:
            List of summary strings (one per chunk)
        """
        summaries = []
        batch_size = settings.chunk_batch_size

        for i in range(0, len(narrative_chunks), batch_size):
            batch = narrative_chunks[i:i+batch_size]
            batch_data = [
                {"page": chunk.metadata["page_number"], "text": chunk.narrative_text}
                for chunk in batch
            ]

            logger.info(
                f"Summarizing narrative batch {i//batch_size + 1} ({len(batch)} chunks)",
                extra={"request_id": request_id}
            )

            batch_summaries = await self.llm_client.summarize_chunks_batch(batch_data)
            summaries.extend(batch_summaries)

        return summaries

    def _build_combined_context(
        self,
        narrative_chunks: list,
        narrative_summaries: list[str],
        table_chunks: list,
        original_char_count: int
    ) -> tuple[str, dict]:
        """Build combined context for expensive LLM from summaries and tables.

        Format:
        === DOCUMENT SUMMARIES (Narrative) ===
        [Page 1] Summary...
        [Page 2] Summary...

        === FINANCIAL TABLES (Complete Data) ===
        [Page 5] Table data...

        Args:
            narrative_chunks: Original narrative chunks
            narrative_summaries: Summaries from cheap LLM
            table_chunks: Chunks containing tables (raw, not summarized)
            original_char_count: Total chars before compression

        Returns:
            Tuple of (combined_text, metadata_dict)
        """
        combined_sections = []

        # Add narrative summaries
        if narrative_summaries:
            combined_sections.append("=== DOCUMENT SUMMARIES (Narrative) ===\n")
            for i, chunk in enumerate(narrative_chunks):
                page_num = chunk.metadata["page_number"]
                summary = narrative_summaries[i] if i < len(narrative_summaries) else chunk.narrative_text
                combined_sections.append(f"[Page {page_num}]\n{summary}\n")

        # Add table chunks (raw, untouched)
        if table_chunks:
            combined_sections.append("\n=== FINANCIAL TABLES (Complete Data) ===\n")
            for chunk in table_chunks:
                page_num = chunk.metadata["page_number"]
                table_count = chunk.metadata["table_count"]
                combined_sections.append(
                    f"[Page {page_num} - Contains {table_count} table(s)]\n{chunk.text}\n"
                )

        combined_text = "\n".join(combined_sections)

        compression_ratio = (
            (1 - len(combined_text) / original_char_count) * 100
            if original_char_count > 0 else 0
        )

        metadata = {
            "original_chars": original_char_count,
            "compressed_chars": len(combined_text),
            "compression_ratio": f"{compression_ratio:.1f}%",
            "narrative_chunks": len(narrative_chunks),
            "table_chunks": len(table_chunks),
            "narrative_summaries": len(narrative_summaries),
        }

        return combined_text, metadata
