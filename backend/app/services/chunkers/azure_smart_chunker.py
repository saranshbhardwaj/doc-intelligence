"""Azure Smart Chunker with section-based chunking and rich metadata.

Implements intelligent chunking strategy:
1. Groups content by sections (using sectionHeading paragraphs)
2. Respects size limits (~500 tokens per chunk)
3. Tracks continuation chunks with parent relationships
4. Links tables to their narrative context
5. Populates rich chunk_metadata for retrieval
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from app.services.chunkers.base import (
    DocumentChunker,
    Chunk,
    ChunkingOutput,
    ChunkStrategy,
)
from app.services.parsers.base import ParserOutput
from app.utils.chunk_metadata import (
    ChunkMetadataBuilder,
    estimate_tokens,
    generate_chunk_id,
)
from app.utils.logging import logger


@dataclass
class SectionGroup:
    """A group of paragraphs under a section heading."""
    section_id: str
    section_heading: Optional[str]
    paragraphs: List[Dict]  # Paragraph dicts from parser
    tables: List[Dict]  # Tables in this section
    page_range: List[int]  # [start_page, end_page]
    total_tokens: int


class AzureSmartChunker(DocumentChunker):
    """
    Smart chunker for Azure Document Intelligence parser output.

    Strategy:
    1. Group paragraphs by sections (using sectionHeading role)
    2. For each section:
       - If section fits in token limit → single chunk
       - If section exceeds limit → split into continuation chunks
    3. Create separate chunks for tables (linked to narrative)
    4. Populate rich metadata for all chunks

    Configuration:
    - max_tokens: Maximum tokens per narrative chunk (default: 500)
    - include_page_headers: Include page headers in chunks (default: False)
    - link_tables_to_narrative: Link table chunks to narrative (default: True)
    """

    def __init__(
        self,
        max_tokens: int = 500,
        include_page_headers: bool = False,
        link_tables_to_narrative: bool = True
    ):
        self.max_tokens = max_tokens
        self.include_page_headers = include_page_headers
        self.link_tables_to_narrative = link_tables_to_narrative

        logger.info(
            f"AzureSmartChunker initialized: max_tokens={max_tokens}, "
            f"include_headers={include_page_headers}, link_tables={link_tables_to_narrative}"
        )

    def chunk(self, parser_output: ParserOutput) -> ChunkingOutput:
        """
        Chunk Azure parser output using smart section-based strategy.

        Args:
            parser_output: Output from AzureDocumentIntelligenceParser

        Returns:
            ChunkingOutput with smart chunks and rich metadata
        """
        logger.info(f"Smart chunking {parser_output.page_count} pages")

        # Extract enhanced structure
        metadata = parser_output.metadata or {}
        enhanced_pages = metadata.get("enhanced_pages", [])
        structured_data = metadata.get("structured_data", {})

        if not enhanced_pages:
            raise ValueError(
                "Azure parser output missing 'enhanced_pages'. "
                "Ensure you're using the enhanced AzureDocumentIntelligenceParser."
            )

        # Step 1: Group content by sections
        section_groups = self._group_by_sections(enhanced_pages, structured_data)
        logger.info(f"Identified {len(section_groups)} section groups")

        # Check if document has clear structure
        # If only 1 section with no heading = unstructured doc (e.g., plain Word doc)
        is_unstructured = (
            len(section_groups) == 1 and
            section_groups[0].section_heading is None
        )

        if is_unstructured and section_groups[0].total_tokens > self.max_tokens:
            logger.warning(
                f"Document appears unstructured (no section headings). "
                f"Using sentence-based fallback chunking for {section_groups[0].total_tokens} tokens"
            )
            # Use fallback chunking for unstructured documents
            narrative_chunks = self._fallback_chunking(section_groups[0])
        else:
            # Step 2: Create narrative chunks (with size limits & continuations)
            narrative_chunks = []
            for section_group in section_groups:
                section_chunks = self._chunk_section(section_group)
                narrative_chunks.extend(section_chunks)

        logger.info(f"Created {len(narrative_chunks)} narrative chunks")

        # Step 3: Create table chunks (separate from narrative)
        table_chunks = self._create_table_chunks(enhanced_pages, narrative_chunks)
        logger.info(f"Created {len(table_chunks)} table chunks")

        # Step 4: Combine and link chunks
        all_chunks = narrative_chunks + table_chunks

        # Update sibling relationships
        self._update_sibling_relationships(all_chunks)

        logger.info(
            f"Smart chunking complete: {len(all_chunks)} total chunks "
            f"({len(narrative_chunks)} narrative, {len(table_chunks)} tables)"
        )

        return ChunkingOutput(
            chunks=all_chunks,
            strategy=ChunkStrategy.SEMANTIC,  # Section-based is semantic
            metadata={
                "source_parser": parser_output.parser_name,
                "chunking_strategy": "section_based_with_size_limits",
                "max_tokens": self.max_tokens,
                "total_sections": len(section_groups),
                "total_narrative_chunks": len(narrative_chunks),
                "total_table_chunks": len(table_chunks),
                "continuation_chunks": sum(
                    1 for c in narrative_chunks
                    if c.metadata.get("is_continuation")
                ),
            }
        )

    def _group_by_sections(
        self,
        enhanced_pages: List[Dict],
        structured_data: Dict
    ) -> List[SectionGroup]:
        """
        Group paragraphs by sections using sectionHeading role.

        Args:
            enhanced_pages: Enhanced page data from parser
            structured_data: Structured data (paragraphs, sections, figures)

        Returns:
            List of SectionGroup objects
        """
        section_groups = []
        current_section_id = "sec_0"  # For content before first heading
        current_section_heading = None
        current_paragraphs = []
        current_tables = []
        current_page_range = []

        all_paragraphs = structured_data.get("paragraphs", [])

        for page in enhanced_pages:
            page_num = page["page_number"]
            paragraphs_by_role = page.get("paragraphs_by_role", {})

            # Track page range
            if not current_page_range:
                current_page_range = [page_num, page_num]
            else:
                current_page_range[1] = page_num

            # Check for section heading (starts new section)
            section_headings = paragraphs_by_role.get("sectionHeading", [])
            if section_headings:
                # Save current section if it has content
                if current_paragraphs:
                    section_groups.append(SectionGroup(
                        section_id=current_section_id,
                        section_heading=current_section_heading,
                        paragraphs=current_paragraphs,
                        tables=current_tables,
                        page_range=current_page_range.copy(),
                        total_tokens=self._estimate_section_tokens(current_paragraphs)
                    ))

                # Start new section
                section_num = len(section_groups) + 1
                current_section_id = f"sec_{section_num}"
                current_section_heading = section_headings[0]["content"]
                current_paragraphs = []
                current_tables = []
                current_page_range = [page_num, page_num]

            # Add content paragraphs to current section
            content_paragraphs = paragraphs_by_role.get("content", [])
            current_paragraphs.extend(content_paragraphs)

            # Add title if present (and not already added)
            if paragraphs_by_role.get("title") and not current_section_heading:
                title_paras = paragraphs_by_role.get("title", [])
                current_paragraphs.extend(title_paras)

            # Add tables to current section
            page_tables = page.get("tables", [])
            for table in page_tables:
                # Add page number to table metadata
                table["page_number"] = page_num
                current_tables.append(table)

        # Add final section
        if current_paragraphs or current_tables:
            section_groups.append(SectionGroup(
                section_id=current_section_id,
                section_heading=current_section_heading,
                paragraphs=current_paragraphs,
                tables=current_tables,
                page_range=current_page_range,
                total_tokens=self._estimate_section_tokens(current_paragraphs)
            ))

        return section_groups

    def _chunk_section(self, section: SectionGroup) -> List[Chunk]:
        """
        Chunk a section, splitting if needed to respect token limits.

        Args:
            section: SectionGroup to chunk

        Returns:
            List of chunks for this section
        """
        # If section fits in token limit, create single chunk
        if section.total_tokens <= self.max_tokens:
            return [self._create_section_chunk(section, sequence=1, total=1)]

        # Section too large, split into continuation chunks
        return self._split_section(section)

    def _create_section_chunk(
        self,
        section: SectionGroup,
        sequence: int,
        total: int,
        parent_chunk_id: Optional[str] = None
    ) -> Chunk:
        """
        Create a chunk for a section (or part of a section).

        Args:
            section: SectionGroup
            sequence: Chunk sequence (1, 2, 3, ...)
            total: Total chunks in this section
            parent_chunk_id: Parent chunk ID (for continuations)

        Returns:
            Chunk object with rich metadata
        """
        # Build chunk text
        chunk_text = self._build_chunk_text(section, sequence, total)

        # Generate chunk ID
        chunk_id = generate_chunk_id(section.section_id, sequence, "para")

        # Build metadata
        builder = ChunkMetadataBuilder()
        builder.set_section_id(section.section_id)
        builder.set_sequence(sequence, total)

        if section.section_heading:
            builder.set_heading_hierarchy([section.section_heading])

        if sequence > 1 and parent_chunk_id:
            builder.mark_continuation(parent_chunk_id)

        builder.set_page_range(section.page_range[0], section.page_range[1])

        # Extract bounding box from section paragraphs for PDF highlighting
        bbox = self._calculate_section_bbox(section)
        if bbox:
            builder.set_bbox(
                page=bbox["page"],
                x0=bbox["x0"],
                y0=bbox["y0"],
                x1=bbox["x1"],
                y1=bbox["y1"]
            )

        chunk_metadata = builder.build()

        # Create chunk - merge chunk_metadata into base metadata
        base_metadata = {
            "page_number": section.page_range[0],
            "page_range": section.page_range,
            "section_heading": section.section_heading,
            "section_type": "narrative",
            "is_tabular": False,
            "char_count": len(chunk_text),
            "token_count": estimate_tokens(chunk_text),
            "chunk_type": "narrative",
            "has_tables": False,
            "source_parser": "azure_document_intelligence",
        }
        # Merge chunk_metadata fields directly (not nested!)
        base_metadata.update(chunk_metadata)

        return Chunk(
            chunk_id=chunk_id,
            text=chunk_text,
            narrative_text=chunk_text,  # No tables in narrative chunks
            tables=None,
            metadata=base_metadata
        )

    def _split_section(self, section: SectionGroup) -> List[Chunk]:
        """
        Split a large section into multiple continuation chunks.

        Strategy:
        - Split at paragraph boundaries
        - Each chunk ≤ max_tokens
        - Carry forward section heading to each chunk
        - Link chunks as parent-child

        Args:
            section: Large SectionGroup to split

        Returns:
            List of continuation chunks
        """
        chunks = []
        current_paragraphs = []
        current_tokens = 0

        for para in section.paragraphs:
            para_tokens = estimate_tokens(para.get("content", ""))

            # Check if adding this paragraph exceeds limit
            if current_tokens + para_tokens > self.max_tokens and current_paragraphs:
                # Create chunk from accumulated paragraphs
                sub_section = SectionGroup(
                    section_id=section.section_id,
                    section_heading=section.section_heading,
                    paragraphs=current_paragraphs,
                    tables=[],  # Tables separate
                    page_range=section.page_range,
                    total_tokens=current_tokens
                )

                chunk = self._create_section_chunk(
                    sub_section,
                    sequence=len(chunks) + 1,
                    total=0,  # Will update later
                    parent_chunk_id=chunks[-1].chunk_id if chunks else None
                )
                chunks.append(chunk)

                # Start new chunk
                current_paragraphs = [para]
                current_tokens = para_tokens
            else:
                current_paragraphs.append(para)
                current_tokens += para_tokens

        # Create final chunk
        if current_paragraphs:
            sub_section = SectionGroup(
                section_id=section.section_id,
                section_heading=section.section_heading,
                paragraphs=current_paragraphs,
                tables=[],
                page_range=section.page_range,
                total_tokens=current_tokens
            )

            chunk = self._create_section_chunk(
                sub_section,
                sequence=len(chunks) + 1,
                total=0,
                parent_chunk_id=chunks[-1].chunk_id if chunks else None
            )
            chunks.append(chunk)

        # Update total_chunks_in_section for all chunks
        for chunk in chunks:
            chunk.metadata["total_chunks_in_section"] = len(chunks)

        return chunks

    def _fallback_chunking(self, section: SectionGroup) -> List[Chunk]:
        """
        Fallback chunking for unstructured documents (e.g., Word docs with no headings).

        Strategy:
        - Split text at sentence boundaries using simple heuristics
        - Group sentences into ~max_tokens chunks
        - Mark as continuation chunks

        Args:
            section: The unstructured section to chunk

        Returns:
            List of chunks split at sentence boundaries
        """
        # Combine all paragraph text
        full_text = "\n\n".join(
            para.get("content", "") for para in section.paragraphs
        )

        # Simple sentence splitting (periods followed by space/newline)
        # Note: Not perfect but works for most cases without NLTK dependency
        import re
        sentences = re.split(r'(?<=[.!?])\s+', full_text)

        chunks = []
        current_sentences = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = estimate_tokens(sentence)

            # If adding this sentence exceeds limit, create a chunk
            if current_tokens + sentence_tokens > self.max_tokens and current_sentences:
                # Create chunk from accumulated sentences
                chunk_text = " ".join(current_sentences)
                chunk = self._create_fallback_chunk(
                    chunk_text,
                    section,
                    sequence=len(chunks) + 1,
                    parent_chunk_id=chunks[-1].chunk_id if chunks else None
                )
                chunks.append(chunk)

                # Start new chunk
                current_sentences = [sentence]
                current_tokens = sentence_tokens
            else:
                current_sentences.append(sentence)
                current_tokens += sentence_tokens

        # Create final chunk
        if current_sentences:
            chunk_text = " ".join(current_sentences)
            chunk = self._create_fallback_chunk(
                chunk_text,
                section,
                sequence=len(chunks) + 1,
                parent_chunk_id=chunks[-1].chunk_id if chunks else None
            )
            chunks.append(chunk)

        # Update total for all chunks
        for chunk in chunks:
            chunk.metadata["total_chunks_in_section"] = len(chunks)

        logger.info(
            f"Fallback chunking created {len(chunks)} chunks from unstructured document"
        )

        return chunks

    def _create_fallback_chunk(
        self,
        text: str,
        section: SectionGroup,
        sequence: int,
        parent_chunk_id: Optional[str] = None
    ) -> Chunk:
        """Create a chunk for fallback (unstructured) chunking."""
        chunk_id = generate_chunk_id(section.section_id, sequence, "fallback")

        # Build metadata
        builder = ChunkMetadataBuilder()
        builder.set_section_id(section.section_id)
        builder.set_sequence(sequence, total=0)  # Will update later

        if sequence > 1 and parent_chunk_id:
            builder.mark_continuation(parent_chunk_id)

        builder.set_page_range(section.page_range[0], section.page_range[1])

        chunk_metadata = builder.build()

        # Merge metadata
        base_metadata = {
            "page_number": section.page_range[0],
            "page_range": section.page_range,
            "section_type": "narrative",
            "is_tabular": False,
            "char_count": len(text),
            "token_count": estimate_tokens(text),
            "chunk_type": "narrative",
            "has_tables": False,
            "source_parser": "azure_document_intelligence",
            "chunking_strategy": "fallback_sentence_based",  # Mark as fallback
        }
        base_metadata.update(chunk_metadata)

        return Chunk(
            chunk_id=chunk_id,
            text=text,
            narrative_text=text,
            tables=None,
            metadata=base_metadata
        )

    def _create_table_chunks(
        self,
        enhanced_pages: List[Dict],
        narrative_chunks: List[Chunk]
    ) -> List[Chunk]:
        """
        Create separate chunks for tables.

        Args:
            enhanced_pages: Enhanced page data
            narrative_chunks: Narrative chunks (for linking)

        Returns:
            List of table chunks
        """
        table_chunks = []
        table_counter = 0

        for page in enhanced_pages:
            page_num = page["page_number"]
            tables = page.get("tables", [])

            for table_data in tables:
                table_counter += 1

                # Find preceding narrative chunk (for context)
                preceding_narrative = self._find_preceding_narrative(
                    page_num, narrative_chunks
                )

                # Build table text
                table_text = f"[Table {table_counter}]\n{table_data.get('text', '')}"

                # Extract table context (preceding paragraph if available)
                table_context = self._extract_table_context(page, table_data)

                # Build metadata
                builder = ChunkMetadataBuilder()
                builder.set_section_id(f"table_{table_counter}")
                builder.set_table_metadata(
                    context=table_context,
                    row_count=table_data.get("row_count"),
                    column_count=table_data.get("column_count")
                )

                # Extract table bounding box for PDF highlighting
                table_bbox = self._extract_table_bbox(table_data)
                if table_bbox:
                    builder.set_bbox(
                        page=page_num,
                        x0=table_bbox["x0"],
                        y0=table_bbox["y0"],
                        x1=table_bbox["x1"],
                        y1=table_bbox["y1"]
                    )

                if preceding_narrative:
                    builder.link_to_narrative(preceding_narrative.chunk_id)

                chunk_metadata = builder.build()

                # Create table chunk - merge chunk_metadata into base metadata
                base_metadata = {
                    "page_number": page_num,
                    "section_type": "table",
                    "is_tabular": True,
                    "char_count": len(table_text),
                    "token_count": estimate_tokens(table_text),
                    "chunk_type": "table",
                    "has_tables": True,
                    "table_count": 1,
                    "source_parser": "azure_document_intelligence",
                }
                # Merge chunk_metadata fields directly
                base_metadata.update(chunk_metadata)

                chunk = Chunk(
                    chunk_id=generate_chunk_id(f"page_{page_num}", table_counter, "table"),
                    text=table_text,
                    narrative_text="",  # No narrative in table chunks
                    tables=[table_data],
                    metadata=base_metadata
                )

                table_chunks.append(chunk)

                # Link narrative chunk to this table (bidirectional)
                if preceding_narrative and self.link_tables_to_narrative:
                    linked_tables = preceding_narrative.metadata.get("linked_table_ids", [])
                    linked_tables.append(chunk.chunk_id)
                    preceding_narrative.metadata["linked_table_ids"] = linked_tables

        return table_chunks

    def _update_sibling_relationships(self, chunks: List[Chunk]) -> None:
        """
        Update sibling_chunk_ids for chunks in the same section.

        Args:
            chunks: All chunks (modifies in place)
        """
        # Group chunks by section_id
        chunks_by_section: Dict[str, List[str]] = {}

        for chunk in chunks:
            section_id = chunk.metadata.get("section_id")

            if section_id:
                chunks_by_section.setdefault(section_id, []).append(chunk.chunk_id)

        # Update each chunk with its siblings
        for chunk in chunks:
            section_id = chunk.metadata.get("section_id")

            if section_id and section_id in chunks_by_section:
                chunk.metadata["sibling_chunk_ids"] = chunks_by_section[section_id]

    def _find_preceding_narrative(
        self,
        page_num: int,
        narrative_chunks: List[Chunk]
    ) -> Optional[Chunk]:
        """Find the narrative chunk preceding this table."""
        for chunk in reversed(narrative_chunks):
            chunk_page = chunk.metadata.get("page_number", 0)
            if chunk_page <= page_num:
                return chunk
        return None

    def _extract_table_context(self, page: Dict, table_data: Dict) -> str:
        """
        Extract context for a table (preceding paragraph).

        Args:
            page: Enhanced page data
            table_data: Table data

        Returns:
            Context string (preceding paragraph or empty)
        """
        # Get content paragraphs
        paragraphs_by_role = page.get("paragraphs_by_role", {})
        content_paras = paragraphs_by_role.get("content", [])

        # Return first content paragraph as context (simple heuristic)
        if content_paras:
            return content_paras[0].get("content", "")[:200]  # First 200 chars

        return ""

    def _build_chunk_text(
        self,
        section: SectionGroup,
        sequence: int,
        total: int
    ) -> str:
        """
        Build text for a chunk.

        Always includes section heading (for context in continuations).

        Args:
            section: SectionGroup
            sequence: Chunk sequence
            total: Total chunks in section

        Returns:
            Chunk text string
        """
        lines = []

        # Always include section heading (if present)
        if section.section_heading:
            lines.append(section.section_heading)
            lines.append("")  # Blank line

        # Add paragraph content
        for para in section.paragraphs:
            content = para.get("content", "")
            if content:
                lines.append(content)

        return "\n".join(lines)

    def _estimate_section_tokens(self, paragraphs: List[Dict]) -> int:
        """Estimate total tokens in a section."""
        total_chars = sum(len(p.get("content", "")) for p in paragraphs)
        return estimate_tokens(" " * total_chars)  # Rough estimate

    def _calculate_section_bbox(self, section: SectionGroup) -> Optional[Dict]:
        """
        Calculate bounding box for a section from its paragraph bounding regions.

        Strategy:
        - Collect all bounding_regions from section paragraphs
        - Convert polygons to bbox coordinates (x0, y0, x1, y1)
        - Merge into single bbox covering the entire section

        Args:
            section: SectionGroup with paragraphs containing bounding_regions

        Returns:
            Dict with {page, x0, y0, x1, y1} or None if no bounding regions
        """
        all_bboxes = []

        for para in section.paragraphs:
            bounding_regions = para.get("bounding_regions", [])

            for br in bounding_regions:
                polygon = br.get("polygon", [])
                page_num = br.get("page_number")

                if len(polygon) == 8 and page_num:
                    # Convert polygon to bbox
                    bbox = self._polygon_to_bbox(polygon)
                    bbox["page"] = page_num
                    all_bboxes.append(bbox)

        if not all_bboxes:
            return None

        # Merge all bboxes (use first page if multi-page section)
        primary_page = section.page_range[0]
        page_bboxes = [b for b in all_bboxes if b["page"] == primary_page]

        if not page_bboxes:
            return None

        # Calculate bounding box covering all paragraphs on primary page
        return {
            "page": primary_page,
            "x0": min(b["x0"] for b in page_bboxes),
            "y0": min(b["y0"] for b in page_bboxes),
            "x1": max(b["x1"] for b in page_bboxes),
            "y1": max(b["y1"] for b in page_bboxes)
        }

    def _polygon_to_bbox(self, polygon: List[float]) -> Dict:
        """
        Convert 8-point polygon to rectangular bounding box.

        Args:
            polygon: List of 8 floats [x1, y1, x2, y2, x3, y3, x4, y4]

        Returns:
            Dict with {x0, y0, x1, y1} representing min/max coordinates
        """
        x_coords = [polygon[i] for i in range(0, 8, 2)]  # [x1, x2, x3, x4]
        y_coords = [polygon[i] for i in range(1, 8, 2)]  # [y1, y2, y3, y4]

        return {
            "x0": min(x_coords),  # Left edge
            "y0": min(y_coords),  # Top edge
            "x1": max(x_coords),  # Right edge
            "y1": max(y_coords)   # Bottom edge
        }

    def _extract_table_bbox(self, table_data: Dict) -> Optional[Dict]:
        """
        Extract bounding box from table data.

        Args:
            table_data: Table data from enhanced_pages

        Returns:
            Dict with {x0, y0, x1, y1} or None
        """
        # Check if table has bounding_regions (after parser enhancement)
        bounding_regions = table_data.get("bounding_regions", [])

        if not bounding_regions:
            return None

        # Convert first bounding region to bbox
        br = bounding_regions[0]
        polygon = br.get("polygon", [])

        if len(polygon) == 8:
            return self._polygon_to_bbox(polygon)

        return None

    @property
    def name(self) -> str:
        return "azure_smart_chunker"

    @property
    def strategy(self) -> ChunkStrategy:
        return ChunkStrategy.SEMANTIC

    def supports_parser(self, parser_name: str) -> bool:
        """This chunker supports Azure Document Intelligence parser."""
        return parser_name == "azure_document_intelligence"
