"""Base classes for document chunking.

Chunkers take ParserOutput and split it into processable chunks for LLM processing.
Different parsers may require different chunking strategies based on their output structure.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

from app.services.parsers.base import ParserOutput


class ChunkType(str, Enum):
    """Type of chunk content"""
    NARRATIVE = "narrative"  # Text-only chunk
    TABLE = "table"          # Contains table data
    MIXED = "mixed"          # Both narrative and tables


class ChunkStrategy(str, Enum):
    """Chunking strategy used"""
    PAGE_WISE = "page_wise"        # One chunk per page
    SEMANTIC = "semantic"          # Semantic similarity-based
    FIXED_SIZE = "fixed_size"      # Fixed character/token count
    HYBRID = "hybrid"              # Combination of strategies


@dataclass
class Chunk:
    """A chunk of document content.

    Design philosophy:
    - `text`: Full text including tables (for LLM context when needed)
    - `narrative_text`: Text without tables (for cheap LLM summarization)
    - `tables`: Separate table data (preserved in raw form for expensive LLM)
    """
    chunk_id: str
    text: str  # Full text with tables embedded
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Optional: separated content for flexible processing
    narrative_text: Optional[str] = None  # Text without tables
    tables: Optional[List[Dict[str, Any]]] = None  # Separate table data

    @property
    def chunk_type(self) -> ChunkType:
        """Determine chunk type based on content."""
        has_tables = self.metadata.get("has_tables", False)
        has_narrative = bool(self.narrative_text and self.narrative_text.strip())

        if has_tables and has_narrative:
            return ChunkType.MIXED
        elif has_tables:
            return ChunkType.TABLE
        else:
            return ChunkType.NARRATIVE

    @property
    def char_count(self) -> int:
        """Total character count of full text."""
        return len(self.text)

    @property
    def narrative_char_count(self) -> int:
        """Character count of narrative text only."""
        return len(self.narrative_text) if self.narrative_text else 0


@dataclass
class ChunkingOutput:
    """Output from document chunker."""
    chunks: List[Chunk]
    strategy: ChunkStrategy
    metadata: Optional[Dict[str, Any]] = None

    @property
    def total_chunks(self) -> int:
        """Total number of chunks."""
        return len(self.chunks)

    @property
    def total_chars(self) -> int:
        """Total character count across all chunks."""
        return sum(chunk.char_count for chunk in self.chunks)

    @property
    def chunks_with_tables(self) -> int:
        """Count of chunks containing tables."""
        return sum(1 for chunk in self.chunks if chunk.metadata.get("has_tables", False))

    @property
    def total_tables(self) -> int:
        """Total number of tables across all chunks."""
        return sum(chunk.metadata.get("table_count", 0) for chunk in self.chunks)

    def get_narrative_chunks(self) -> List[Chunk]:
        """Get chunks that are narrative-only (no tables)."""
        return [c for c in self.chunks if c.chunk_type == ChunkType.NARRATIVE]

    def get_table_chunks(self) -> List[Chunk]:
        """Get chunks that contain tables."""
        return [c for c in self.chunks if c.metadata.get("has_tables", False)]


class DocumentChunker(ABC):
    """Base class for all document chunkers.

    Each chunker implementation should:
    1. Take ParserOutput as input
    2. Apply a chunking strategy (page-wise, semantic, etc.)
    3. Return ChunkingOutput with list of chunks
    4. Separate narrative text from tables for flexible LLM processing
    """

    @abstractmethod
    def chunk(self, parser_output: ParserOutput) -> ChunkingOutput:
        """Chunk parser output into processable pieces.

        Args:
            parser_output: Output from DocumentParser

        Returns:
            ChunkingOutput with list of chunks

        Raises:
            Exception if chunking fails
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Chunker identifier (e.g., 'azure_page_wise', 'semantic')"""
        pass

    @property
    @abstractmethod
    def strategy(self) -> ChunkStrategy:
        """Chunking strategy used by this chunker"""
        pass

    @abstractmethod
    def supports_parser(self, parser_name: str) -> bool:
        """Check if this chunker supports the given parser's output.

        Args:
            parser_name: Name of the parser (e.g., 'azure_document_intelligence')

        Returns:
            True if this chunker can process output from this parser
        """
        pass
