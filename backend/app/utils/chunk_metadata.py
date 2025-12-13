"""Utility functions for working with chunk metadata.

Provides helpers for:
- Building chunk metadata during chunking
- Querying chunk relationships
- Expanding chunks with related context
"""
from typing import List, Dict, Any, Optional
from app.utils.token_utils import count_tokens
from sqlalchemy.orm import Session
from sqlalchemy import select
import sqlalchemy as sa
from app.db_models_chat import DocumentChunk


class ChunkMetadataBuilder:
    """
    Builder for constructing chunk metadata during chunking.

    Usage:
        builder = ChunkMetadataBuilder()
        builder.set_section_id("sec_2")
        builder.set_sequence(2, total=3)
        builder.mark_continuation(parent_id="chunk_123")
        metadata = builder.build()
    """

    def __init__(self):
        self._metadata: Dict[str, Any] = {}

    def set_section_id(self, section_id: str) -> "ChunkMetadataBuilder":
        """Set the section ID."""
        self._metadata["section_id"] = section_id
        return self

    def set_sequence(self, sequence: int, total: int) -> "ChunkMetadataBuilder":
        """Set chunk sequence within section."""
        self._metadata["chunk_sequence"] = sequence
        self._metadata["total_chunks_in_section"] = total
        return self

    def mark_continuation(self, parent_id: str) -> "ChunkMetadataBuilder":
        """Mark this chunk as a continuation of a parent chunk."""
        self._metadata["is_continuation"] = True
        self._metadata["parent_chunk_id"] = parent_id
        return self

    def set_siblings(self, sibling_ids: List[str]) -> "ChunkMetadataBuilder":
        """Set sibling chunk IDs (chunks in same section)."""
        self._metadata["sibling_chunk_ids"] = sibling_ids
        return self

    def link_to_narrative(self, narrative_id: str) -> "ChunkMetadataBuilder":
        """Link this chunk to a narrative chunk (for table chunks)."""
        self._metadata["linked_narrative_id"] = narrative_id
        return self

    def link_to_tables(self, table_ids: List[str]) -> "ChunkMetadataBuilder":
        """Link this chunk to table chunks (for narrative chunks)."""
        self._metadata["linked_table_ids"] = table_ids
        return self

    def set_heading_hierarchy(self, hierarchy: List[str]) -> "ChunkMetadataBuilder":
        """Set heading hierarchy breadcrumbs."""
        self._metadata["heading_hierarchy"] = hierarchy
        return self

    def set_paragraph_roles(self, roles: List[str]) -> "ChunkMetadataBuilder":
        """Set paragraph roles (e.g., ['sectionHeading', 'content'])."""
        self._metadata["paragraph_roles"] = roles
        return self

    def set_page_range(self, start_page: int, end_page: Optional[int] = None) -> "ChunkMetadataBuilder":
        """Set page range if chunk spans multiple pages."""
        if end_page is None or end_page == start_page:
            self._metadata["page_range"] = [start_page]
        else:
            self._metadata["page_range"] = [start_page, end_page]
        return self

    def set_table_metadata(
        self,
        caption: Optional[str] = None,
        context: Optional[str] = None,
        row_count: Optional[int] = None,
        column_count: Optional[int] = None
    ) -> "ChunkMetadataBuilder":
        """Set table-specific metadata."""
        if caption:
            self._metadata["table_caption"] = caption
        if context:
            self._metadata["table_context"] = context
        if row_count is not None:
            self._metadata["table_row_count"] = row_count
        if column_count is not None:
            self._metadata["table_column_count"] = column_count
        return self

    def set_figure_metadata(
        self,
        figure_id: Optional[str] = None,
        caption: Optional[str] = None
    ) -> "ChunkMetadataBuilder":
        """Set figure-specific metadata."""
        if figure_id:
            self._metadata["figure_id"] = figure_id
        if caption:
            self._metadata["figure_caption"] = caption
        self._metadata["has_figures"] = True
        return self

    def set_content_type(self, content_type: str) -> "ChunkMetadataBuilder":
        """Set inferred content type (e.g., 'financial_table', 'narrative')."""
        self._metadata["content_type"] = content_type
        return self

    def set_custom(self, key: str, value: Any) -> "ChunkMetadataBuilder":
        """Set custom metadata field."""
        self._metadata[key] = value
        return self

    # === Citation Metadata Methods ===

    def set_document_info(
        self,
        filename: str,
        title: Optional[str] = None,
        source_url: Optional[str] = None
    ) -> "ChunkMetadataBuilder":
        """Set document reference information for citations.

        Args:
            filename: Document filename (e.g., "CIM-06-Pizza-Hut.pdf")
            title: Optional document title
            source_url: Optional source URL or file path
        """
        self._metadata["document_filename"] = filename
        if title:
            self._metadata["document_title"] = title
        if source_url:
            self._metadata["source_url"] = source_url
        return self

    def set_page_label(self, page_label: str) -> "ChunkMetadataBuilder":
        """Set page label (supports roman numerals, custom labels).

        Args:
            page_label: Page label as string (e.g., "15", "iii", "A-3")
        """
        self._metadata["page_label"] = page_label
        return self

    def set_citation_snippet(
        self,
        first_sentence: Optional[str] = None,
        summary: Optional[str] = None
    ) -> "ChunkMetadataBuilder":
        """Set citation preview text.

        Args:
            first_sentence: First sentence of chunk (for quick preview)
            summary: Brief summary of chunk content
        """
        if first_sentence:
            self._metadata["first_sentence"] = first_sentence
        if summary:
            self._metadata["content_summary"] = summary
        return self

    def set_bbox(
        self,
        page: int,
        x0: float,
        y0: float,
        x1: float,
        y1: float
    ) -> "ChunkMetadataBuilder":
        """Set bounding box for PDF highlighting.

        Args:
            page: Page number
            x0, y0, x1, y1: Bounding box coordinates
        """
        self._metadata["bbox"] = {
            "page": page,
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1
        }
        return self

    def build(self) -> Dict[str, Any]:
        """Build and return the metadata dict."""
        return self._metadata.copy()


class ChunkRelationshipExpander:
    """
    Expands chunks with related chunks for complete context.

    Usage:
        expander = ChunkRelationshipExpander(db_session)
        expanded_chunks = expander.expand_chunks(initial_chunks)
    """

    def __init__(self, db: Session):
        self.db = db

    def expand_chunks(
        self,
        chunks: List[Dict],
        max_related: int = 5
    ) -> List[Dict]:
        """
        Expand chunks with related chunks (parents, siblings, linked).

        Args:
            chunks: Initial chunks from retrieval
            max_related: Maximum related chunks to fetch per initial chunk

        Returns:
            Expanded list with original + related chunks
        """
        # Collect all chunk IDs to fetch
        chunk_ids_to_fetch = set()

        for chunk in chunks:
            metadata = chunk.get("chunk_metadata") or {}

            # Add parent
            if metadata.get("parent_chunk_id"):
                chunk_ids_to_fetch.add(metadata["parent_chunk_id"])

            # Add siblings (limited to avoid explosion)
            siblings = metadata.get("sibling_chunk_ids", [])
            chunk_ids_to_fetch.update(siblings[:max_related])

            # Add linked narrative
            if metadata.get("linked_narrative_id"):
                chunk_ids_to_fetch.add(metadata["linked_narrative_id"])

            # Add linked tables (limited)
            linked_tables = metadata.get("linked_table_ids", [])
            chunk_ids_to_fetch.update(linked_tables[:max_related])

        # Remove IDs we already have
        existing_ids = {chunk["id"] for chunk in chunks}
        chunk_ids_to_fetch -= existing_ids

        # Fetch related chunks
        if chunk_ids_to_fetch:
            related_chunks = self._fetch_chunks_by_ids(list(chunk_ids_to_fetch))
            return chunks + related_chunks

        return chunks

    def get_section_chunks(
        self,
        section_id: str,
        document_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Get all chunks in a section.

        Args:
            section_id: Section ID to query
            document_id: Optional document filter

        Returns:
            List of chunks in the section
        """
        stmt = select(DocumentChunk).where(
            DocumentChunk.chunk_metadata['section_id'].astext == section_id
        )

        if document_id:
            stmt = stmt.where(DocumentChunk.document_id == document_id)

        # Order by chunk sequence
        stmt = stmt.order_by(
            DocumentChunk.chunk_metadata['chunk_sequence'].astext.cast(sa.Integer)
        )

        results = self.db.execute(stmt).scalars().all()
        return [self._chunk_to_dict(chunk) for chunk in results]

    def get_continuation_chain(self, chunk_id: str) -> List[Dict]:
        """
        Get full continuation chain for a chunk.

        If chunk is part of a sequence, returns all chunks in order:
        [chunk_1, chunk_2, chunk_3, ...]

        Args:
            chunk_id: ID of any chunk in the chain

        Returns:
            List of chunks in sequence order
        """
        # Get the initial chunk
        chunk = self.db.get(DocumentChunk, chunk_id)
        if not chunk or not chunk.chunk_metadata:
            return []

        section_id = chunk.chunk_metadata.get("section_id")
        if not section_id:
            return [self._chunk_to_dict(chunk)]

        # Get all chunks in the section
        return self.get_section_chunks(section_id, document_id=chunk.document_id)

    def _fetch_chunks_by_ids(self, chunk_ids: List[str]) -> List[Dict]:
        """Fetch chunks by IDs from database."""
        if not chunk_ids:
            return []

        stmt = select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
        results = self.db.execute(stmt).scalars().all()

        return [
            {
                **self._chunk_to_dict(chunk),
                "is_related": True,  # Flag to indicate this was fetched via relationship
            }
            for chunk in results
        ]

    def _chunk_to_dict(self, chunk: DocumentChunk) -> Dict:
        """Convert DocumentChunk model to dict."""
        return {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "text": chunk.text,
            "narrative_text": chunk.narrative_text,
            "tables": chunk.tables,
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
            "section_type": chunk.section_type,
            "section_heading": chunk.section_heading,
            "is_tabular": chunk.is_tabular,
            "token_count": chunk.token_count,
            "chunk_metadata": chunk.chunk_metadata,
        }


def estimate_tokens(text: str) -> int:
    """
    Estimate token count from text (rough approximation).

    Rule of thumb: ~4 characters per token for English text.

    Args:
        text: Input text

    Returns:
        Estimated token count
    """
    return count_tokens(text)


def should_split_chunk(text: str, max_tokens: int = 500) -> bool:
    """
    Check if a chunk should be split based on token limit.

    Args:
        text: Chunk text
        max_tokens: Maximum tokens per chunk

    Returns:
        True if chunk exceeds limit
    """
    return estimate_tokens(text) > max_tokens


def generate_chunk_id(section_id: str, sequence: int, chunk_type: str = "para") -> str:
    """
    Generate a descriptive chunk ID.

    Args:
        section_id: Section identifier
        sequence: Sequence number within section
        chunk_type: Type of chunk ('para', 'table', 'figure')

    Returns:
        Chunk ID string (e.g., 'sec_2_para_1', 'sec_2_table_1')
    """
    return f"{section_id}_{chunk_type}_{sequence}"


def validate_and_normalize_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize chunk structure for RAG operations.

    Ensures:
    - chunk_metadata exists and is a dict
    - document_filename is present in metadata
    - JSONB strings are deserialized

    Args:
        chunk: Raw chunk dict from retrieval

    Returns:
        Normalized chunk dict with guaranteed structure
    """
    import json
    from app.utils.logging import logger

    # Ensure chunk_metadata exists
    if "chunk_metadata" not in chunk or chunk["chunk_metadata"] is None:
        chunk["chunk_metadata"] = {}

    # Deserialize JSONB if it came as string
    elif isinstance(chunk["chunk_metadata"], str):
        try:
            chunk["chunk_metadata"] = json.loads(chunk["chunk_metadata"])
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                f"Failed to parse chunk_metadata JSON, using empty dict: {e}",
                extra={"chunk_id": chunk.get("id")}
            )
            chunk["chunk_metadata"] = {}

    # Ensure metadata is a dict
    if not isinstance(chunk["chunk_metadata"], dict):
        logger.warning(
            f"chunk_metadata is not a dict (type: {type(chunk['chunk_metadata'])}), using empty dict",
            extra={"chunk_id": chunk.get("id")}
        )
        chunk["chunk_metadata"] = {}

    # Ensure document_filename exists (fallback to document_id or Unknown)
    if "document_filename" not in chunk["chunk_metadata"]:
        filename = chunk.get("document_id", "Unknown")
        chunk["chunk_metadata"]["document_filename"] = filename

        logger.debug(
            f"Added missing document_filename to chunk_metadata: {filename}",
            extra={"chunk_id": chunk.get("id"), "document_id": chunk.get("document_id")}
        )

    return chunk


def validate_and_normalize_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate and normalize a list of chunks.

    Args:
        chunks: List of raw chunk dicts from retrieval

    Returns:
        List of normalized chunk dicts
    """
    from app.utils.logging import logger

    if not chunks:
        return chunks

    normalized = []
    for chunk in chunks:
        try:
            normalized.append(validate_and_normalize_chunk(chunk))
        except Exception as e:
            logger.error(
                f"Failed to normalize chunk, skipping: {e}",
                extra={"chunk_id": chunk.get("id")},
                exc_info=True
            )
            # Skip malformed chunks rather than crashing
            continue

    logger.debug(
        f"Normalized {len(normalized)} chunks (skipped {len(chunks) - len(normalized)} malformed)"
    )

    return normalized
