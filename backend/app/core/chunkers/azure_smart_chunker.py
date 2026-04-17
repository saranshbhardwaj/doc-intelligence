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

from app.core.chunkers.base import (
    DocumentChunker,
    Chunk,
    ChunkingOutput,
    ChunkStrategy,
)
from app.core.parsers.base import ParserOutput
from app.utils.chunk_metadata import (
    ChunkMetadataBuilder,
    generate_chunk_id,
)
from app.utils.logging import logger
from app.utils.token_utils import count_tokens, truncate_to_token_limit


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

    _BOILERPLATE_HEADINGS = {
        "table of contents",
        "contents",
        "confidential",
        "disclaimer",
    }

    def __init__(
        self,
        max_tokens: int = 500,
        include_page_headers: bool = False,
        link_tables_to_narrative: bool = True,
        overlap_paragraphs: int = 1,
        overlap_sentences: int = 2,
    ):
        self.max_tokens = max_tokens
        self.include_page_headers = include_page_headers
        self.link_tables_to_narrative = link_tables_to_narrative
        self.overlap_paragraphs = overlap_paragraphs
        self.overlap_sentences = overlap_sentences

        logger.info(
            f"AzureSmartChunker initialized: max_tokens={max_tokens}, "
            f"include_headers={include_page_headers}, link_tables={link_tables_to_narrative}, "
            f"overlap_paragraphs={overlap_paragraphs}, overlap_sentences={overlap_sentences}"
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
        table_chunks = self._create_table_chunks(section_groups, narrative_chunks)
        logger.info(f"Created {len(table_chunks)} table chunks")

        # Step 3.5: Create key-value chunks from Azure DI
        kv_pairs = metadata.get("key_value_pairs", [])
        kv_chunks = self._create_key_value_chunks(kv_pairs, len(narrative_chunks) + len(table_chunks))
        logger.info(f"Created {len(kv_chunks)} key-value chunks from {len(kv_pairs)} pairs")

        # Step 4: Combine and link chunks
        all_chunks = narrative_chunks + table_chunks + kv_chunks

        # Update sibling relationships
        self._update_sibling_relationships(all_chunks)

        logger.info(
            f"Smart chunking complete: {len(all_chunks)} total chunks "
            f"({len(narrative_chunks)} narrative, {len(table_chunks)} tables, {len(kv_chunks)} key-value)"
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
                "total_kv_chunks": len(kv_chunks),
                "total_kv_pairs": len(kv_pairs),
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

            # Add content paragraphs to current section, tagging each with its page number
            # so _find_preceding_paragraph can locate the closest paragraph before any table.
            content_paragraphs = paragraphs_by_role.get("content", [])
            for para in content_paragraphs:
                para["_page_number"] = page_num
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
        # Use accurate tiktoken count on actual built text — the rough char-based
        # estimate (total_tokens) can undercount dense legal text 2-3x, producing
        # single chunks that exceed OpenAI's 8192-token embedding limit.
        actual_text = self._build_chunk_text(section, 1, 1)
        if count_tokens(actual_text) <= self.max_tokens:
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
        # Build chunk text with per-paragraph page tracking
        chunk_text, paragraph_pages = self._build_chunk_text_with_pages(section)

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

        # Store per-paragraph page info for accurate citations and PDF highlighting.
        # Each entry: {"page": N, "char_offset": M, "bbox": {x0, y0, x1, y1}}
        if paragraph_pages:
            builder.set_custom("paragraph_pages", paragraph_pages)

        # Chunk-level bbox: use the first page's merged bbox (for backward-compat highlighting)
        first_page_entry = paragraph_pages[0] if paragraph_pages else None
        if first_page_entry and first_page_entry.get("bbox"):
            fb = first_page_entry["bbox"]
            builder.set_bbox(
                page=first_page_entry["page"],
                x0=fb["x0"],
                y0=fb["y0"],
                x1=fb["x1"],
                y1=fb["y1"]
            )
        else:
            # Fallback to existing merged bbox calculation
            para_bbox = self._calculate_paragraph_bbox(section.paragraphs)
            if para_bbox:
                builder.set_bbox(
                    page=para_bbox["page"],
                    x0=para_bbox["x0"],
                    y0=para_bbox["y0"],
                    x1=para_bbox["x1"],
                    y1=para_bbox["y1"]
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
            "token_count": count_tokens(chunk_text),
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
        - Overlap last N paragraphs from previous chunk into next chunk

        Args:
            section: Large SectionGroup to split

        Returns:
            List of continuation chunks
        """
        chunks = []
        current_paragraphs = []
        current_tokens = 0

        for para in section.paragraphs:
            para_tokens = count_tokens(para.get("content", ""))

            # Hard clamp: a single paragraph larger than max_tokens would bypass
            # the split logic (since current_paragraphs is empty). Truncate it.
            if para_tokens > self.max_tokens:
                logger.warning(
                    f"[CHUNKER] Oversized paragraph ({para_tokens} tokens > {self.max_tokens}), truncating"
                )
                para = {**para, "content": truncate_to_token_limit(para["content"], self.max_tokens)}
                para_tokens = self.max_tokens

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

                # Start new chunk with overlap from previous chunk
                overlap_paras = current_paragraphs[-self.overlap_paragraphs:] if self.overlap_paragraphs > 0 else []
                overlap_tokens = sum(count_tokens(p.get("content", "")) for p in overlap_paras)
                current_paragraphs = overlap_paras + [para]
                current_tokens = overlap_tokens + para_tokens
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
            # Mark overlap metadata on continuation chunks
            if chunk.metadata.get("chunk_sequence", 1) > 1 and self.overlap_paragraphs > 0:
                chunk.metadata["has_overlap"] = True
                chunk.metadata["overlap_paragraphs"] = self.overlap_paragraphs

        return chunks

    def _fallback_chunking(self, section: SectionGroup) -> List[Chunk]:
        """
        Fallback chunking for unstructured documents (e.g., Word docs with no headings).

        Strategy:
        - Split text at sentence boundaries using simple heuristics
        - Group sentences into ~max_tokens chunks
        - Mark as continuation chunks
        - Overlap last N sentences from previous chunk into next chunk

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
            sentence_tokens = count_tokens(sentence)

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

                # Start new chunk with overlap from previous chunk
                overlap_sents = current_sentences[-self.overlap_sentences:] if self.overlap_sentences > 0 else []
                overlap_tokens = sum(count_tokens(s) for s in overlap_sents)
                current_sentences = overlap_sents + [sentence]
                current_tokens = overlap_tokens + sentence_tokens
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
            # Mark overlap metadata on continuation chunks
            if chunk.metadata.get("chunk_sequence", 1) > 1 and self.overlap_sentences > 0:
                chunk.metadata["has_overlap"] = True
                chunk.metadata["overlap_sentences"] = self.overlap_sentences

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
            "token_count": count_tokens(text),
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
        section_groups: List[SectionGroup],
        narrative_chunks: List[Chunk]
    ) -> List[Chunk]:
        """
        Create separate chunks for tables, enriched with section context.

        Each table chunk is prefixed for self-contained semantic retrievability:

          ALL parts  — section heading (5-10 tokens), so any retrieved chunk knows
                       which section it came from without an expander fetch.
          Part 1 only — preceding paragraph snippet (≤150 chars), giving the LLM
                        narrative context. Omitted when a linked narrative chunk
                        exists (context expander handles that at query time).

        Column headers are already repeated by _split_table_by_rows in every split
        group, so data in parts 2+ is interpretable without fetching the parent.

        Token budget is reserved using the full_prefix (part 1, largest) so the
        total chunk size never exceeds max_tokens. Continuation parts link back to
        part 1 via parent_chunk_id (star topology).
        """
        table_chunks = []
        table_counter = 0

        # Tracks the last non-null heading across sections.
        # Pure-table pages (no heading of their own) inherit the nearest preceding heading.
        last_seen_heading: Optional[str] = None
        # Paragraphs from the previous section — fallback context when a table's own
        # section has no text (e.g. a standalone financial summary page).
        prev_section_paragraphs: List[Dict] = []

        for section in section_groups:
            clean_section_heading = self._clean_heading(section.section_heading)
            if clean_section_heading:
                last_seen_heading = clean_section_heading

            # Effective heading: own section first, then nearest ancestor heading.
            effective_heading = clean_section_heading or last_seen_heading

            for table_data in section.tables:
                table_counter += 1
                page_num = table_data.get("page_number")

                # Preceding narrative chunk — used for bidirectional linking and to
                # decide whether to include paragraph text in the prefix.
                preceding_narrative = self._find_preceding_narrative(
                    page_num, narrative_chunks
                )

                # Closest preceding paragraph: same section first, then previous section.
                # Omitted from the prefix when there is a linked narrative (the context
                # expander will fetch the full narrative at retrieval time).
                preceding_para = self._find_preceding_paragraph(
                    section.paragraphs, page_num
                )
                if not preceding_para:
                    preceding_para = self._find_preceding_paragraph(
                        prev_section_paragraphs, page_num + 9999  # any page in prev section
                    )

                # Build two prefix variants:
                #   section_prefix  — heading only; added to EVERY split part so any
                #                     retrieved chunk knows which section it belongs to.
                #   full_prefix     — heading + preceding paragraph; added to part 1 only
                #                     to give the LLM narrative context without bloating
                #                     every continuation chunk.
                # Column headers are already repeated by _split_table_by_rows so data
                # in parts 2+ is independently interpretable without fetching the parent.
                section_prefix = effective_heading or ""
                full_prefix_lines: List[str] = ([section_prefix] if section_prefix else [])
                if preceding_para and not preceding_narrative:
                    # Paragraph snippet capped at 150 chars to leave room for table content.
                    full_prefix_lines.append(preceding_para[:150])
                full_prefix = "\n".join(full_prefix_lines)

                # Reserve the larger (full_prefix) token budget so that part 1 — which
                # carries the most context — never exceeds max_tokens.
                prefix_tokens = count_tokens(full_prefix) if full_prefix else 0
                content_max_tokens = max(self.max_tokens - prefix_tokens, 100)

                # Extract table bounding box for PDF highlighting.
                table_bbox = self._extract_table_bbox(table_data)

                # Split large tables into row-group sub-chunks.
                row_groups = self._split_table_by_rows(table_data, content_max_tokens)
                total_parts = len(row_groups)

                first_chunk_id = None
                created_chunks = []

                for group_idx, group_text in enumerate(row_groups):
                    if total_parts > 1:
                        label = f"[Table {table_counter}, part {group_idx + 1}/{total_parts}]"
                    else:
                        label = f"[Table {table_counter}]"

                    # Part 1: full prefix (heading + paragraph snippet).
                    # Parts 2+: section heading only so any retrieved chunk is section-aware.
                    if group_idx == 0 and full_prefix:
                        chunk_text = f"{full_prefix}\n{label}\n{group_text}"
                    elif group_idx > 0 and section_prefix:
                        chunk_text = f"{section_prefix}\n{label}\n{group_text}"
                    else:
                        chunk_text = f"{label}\n{group_text}"

                    # Build metadata
                    builder = ChunkMetadataBuilder()
                    builder.set_section_id(f"table_{table_counter}")
                    builder.set_table_metadata(
                        context=preceding_para,
                        row_count=table_data.get("row_count"),
                        column_count=table_data.get("column_count")
                    )

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

                    metadata_table_data = table_data.get("table_data", [])[:2]
                    base_metadata = {
                        "page_number": page_num,
                        "section_type": "table",
                        "section_heading": effective_heading,
                        "is_tabular": True,
                        "char_count": len(chunk_text),
                        "token_count": count_tokens(chunk_text),
                        "chunk_type": "table",
                        "has_tables": True,
                        "table_count": 1,
                        "source_parser": "azure_document_intelligence",
                        "table_name": table_data.get("table_name", ""),
                        "column_headers": table_data.get("column_headers", []),
                        "table_data": metadata_table_data,
                    }
                    base_metadata.update(chunk_metadata)

                    # Continuation metadata for split tables — star topology:
                    # all parts link back to part 1 (not a chain) so any part can
                    # reconstruct the table header by fetching parent_chunk_id.
                    if total_parts > 1:
                        base_metadata["is_continuation"] = group_idx > 0
                        base_metadata["parent_chunk_id"] = first_chunk_id if group_idx > 0 else None
                        base_metadata["chunk_sequence"] = group_idx + 1
                        base_metadata["total_chunks_in_section"] = total_parts

                    chunk_id = generate_chunk_id(f"page_{page_num}", table_counter, f"table_{group_idx}")
                    chunk = Chunk(
                        chunk_id=chunk_id,
                        text=chunk_text,
                        narrative_text="",
                        tables=[table_data] if group_idx == 0 else [],  # full data on first sub-chunk only
                        metadata=base_metadata
                    )

                    if group_idx == 0:
                        first_chunk_id = chunk_id
                        logger.debug(
                            "[CHUNKER] Table chunk created",
                            extra={
                                "table_counter": table_counter,
                                "page": page_num,
                                "has_bbox": "bbox" in base_metadata,
                                "parts": total_parts,
                                "has_heading": bool(effective_heading),
                                "has_preceding_para": bool(preceding_para),
                            }
                        )

                    created_chunks.append(chunk)

                table_chunks.extend(created_chunks)

                # Bidirectional link: narrative chunk → first table sub-chunk.
                if preceding_narrative and self.link_tables_to_narrative and created_chunks:
                    linked_tables = preceding_narrative.metadata.get("linked_table_ids", [])
                    linked_tables.append(created_chunks[0].chunk_id)
                    preceding_narrative.metadata["linked_table_ids"] = linked_tables

            # Advance the cross-section paragraph fallback after processing each section.
            if section.paragraphs:
                prev_section_paragraphs = section.paragraphs

        return table_chunks

    def _clean_heading(self, heading: Optional[str]) -> Optional[str]:
        """Return a heading suitable for chunk prefixing, or None if boilerplate."""
        if not heading:
            return None
        normalized = heading.strip()
        if not normalized:
            return None
        lowered = normalized.lower()
        if lowered in self._BOILERPLATE_HEADINGS:
            return None
        if lowered.startswith("table of contents"):
            return None
        return normalized

    def _find_preceding_paragraph(
        self,
        paragraphs: List[Dict],
        table_page: int,
    ) -> str:
        """Return the text of the paragraph closest to and before table_page.

        Paragraphs must have been tagged with '_page_number' by _group_by_sections.
        Returns the last paragraph whose page is <= table_page, capped at 200 chars.
        """
        best: Optional[str] = None
        for para in paragraphs:
            if para.get("_page_number", 0) <= table_page:
                best = para.get("content", "")
        if not best:
            return ""

        cleaned = best.strip()
        # Ignore fragmentary text (single chars, bullets, etc.) as table context.
        if len(cleaned) < 12:
            return ""
        return cleaned[:200]

    def _table_header_lines(self, table_data: dict) -> List[str]:
        """Build stable table title/header lines from structured table metadata."""
        lines: List[str] = []

        table_name = (table_data.get("table_name") or "").strip()
        if table_name:
            lines.append(table_name)

        header_cells = [str(c or "").strip() for c in table_data.get("column_headers", [])]
        non_empty_headers = [c for c in header_cells if c]
        # Include explicit header rows only when they contain multiple non-empty labels.
        if len(non_empty_headers) > 1:
            lines.append("\t".join(header_cells))

        return lines

    def _split_table_by_rows(self, table_data: dict, max_tokens: int) -> List[str]:
        """Split table text into row-group segments of ~max_tokens each.

        Each segment repeats title/header lines so it is self-contained for embedding.
        Falls back to char-truncation when no structured row data is available.
        """
        rows = table_data.get("table_data", [])  # List[List[str]] from Azure DI parser
        full_text = table_data.get("text", "")
        header_lines = self._table_header_lines(table_data)
        header_tokens = sum(count_tokens(line) for line in header_lines)

        if not rows or not full_text:
            # No structured rows — truncate full text as a single group
            if count_tokens(full_text) <= max_tokens:
                return [full_text]
            return [full_text[:max_tokens * 4]]

        groups: List[str] = []
        current_lines: List[str] = list(header_lines)
        current_tokens = header_tokens

        for row in rows:
            row_text = "\t".join(str(c) for c in row)
            row_tokens = count_tokens(row_text)
            if current_tokens + row_tokens > max_tokens and current_lines:
                groups.append("\n".join(current_lines))
                current_lines = list(header_lines)
                current_lines.append(row_text)
                current_tokens = header_tokens + row_tokens
            else:
                current_lines.append(row_text)
                current_tokens += row_tokens

        if current_lines:
            groups.append("\n".join(current_lines))

        return groups if groups else [full_text]

    def _create_key_value_chunks(
        self,
        kv_pairs: List[Dict],
        start_index: int
    ) -> List[Chunk]:
        """
        Create chunks from Azure DI key-value pairs.

        Groups KV pairs by page range (max 100 pairs per chunk) for scalability.
        Each chunk is embedded for RAG while storing structured data for template filling.

        Args:
            kv_pairs: List of key-value pairs from Azure DI
            start_index: Starting chunk index (after narrative + table chunks)

        Returns:
            List of key-value chunks
        """
        if not kv_pairs:
            return []

        kv_chunks = []
        max_kv_pairs_per_chunk = 40
        max_kv_chunk_tokens = max(200, self.max_tokens)

        # Group by page first so citation anchors remain page-accurate.
        kv_by_page: Dict[int, List[Dict]] = {}
        for kv in kv_pairs:
            page_num = kv.get("page_number")
            if not page_num:
                continue
            kv_by_page.setdefault(page_num, []).append(kv)

        for page_num in sorted(kv_by_page.keys()):
            page_pairs = kv_by_page[page_num]
            page_batches = self._split_kv_pairs_by_size(
                page_pairs,
                max_pairs=max_kv_pairs_per_chunk,
                max_tokens=max_kv_chunk_tokens,
            )

            for batch in page_batches:
                # Calculate individual bbox for each KV pair and add to KV data.
                enriched_kv_pairs = []
                for kv in batch:
                    kv_bbox = self._calculate_single_kv_bbox(kv)

                    enriched_kv = dict(kv)
                    if kv_bbox:
                        enriched_kv["bbox"] = kv_bbox

                    enriched_kv_pairs.append(enriched_kv)

                # Build searchable text and include explicit page marker for citation clarity.
                text_lines = [f"[Page {page_num}]"]
                for kv in enriched_kv_pairs:
                    key = kv.get("key", "")
                    value = kv.get("value", "")
                    if key and value:
                        text_lines.append(f"{key}: {value}")
                    elif key:
                        text_lines.append(f"{key}:")

                chunk_text = "\n".join(text_lines)
                page_bbox = self._merge_enriched_kv_bboxes(enriched_kv_pairs, page_num)

                chunk_metadata = {
                    "section_id": f"kv_page_{page_num}",
                    "page_number": page_num,
                    "section_type": "key_value_pairs",
                    "is_tabular": False,
                    "char_count": len(chunk_text),
                    "token_count": count_tokens(chunk_text),
                    "chunk_type": "key_value",
                    "page_range": [page_num, page_num],
                    "key_value_pairs": enriched_kv_pairs,
                    "total_kv_pairs": len(enriched_kv_pairs),
                    "source_parser": "azure_document_intelligence",
                    # Mirror narrative paragraph_pages format for citation resolver compatibility.
                    "kv_pages": [{"page": page_num, "char_offset": 0, "bbox": page_bbox}],
                    "bbox": page_bbox,
                }

                chunk = Chunk(
                    chunk_id=generate_chunk_id("kv_chunk", start_index + len(kv_chunks), "kv"),
                    text=chunk_text,
                    narrative_text="",
                    tables=[],
                    metadata=chunk_metadata,
                )

                kv_chunks.append(chunk)

        if kv_chunks:
            first_chunk_pairs = kv_chunks[0].metadata.get("key_value_pairs", [])
            first_kv = first_chunk_pairs[0] if first_chunk_pairs else None
            if first_kv:
                logger.info(
                    f"[CHUNKER] First KV pair in chunk: '{first_kv.get('key')}', "
                    f"has bbox: {'bbox' in first_kv}, bbox={first_kv.get('bbox')}"
                )

        return kv_chunks

    def _split_kv_pairs_by_size(
        self,
        kv_pairs: List[Dict],
        max_pairs: int,
        max_tokens: int,
    ) -> List[List[Dict]]:
        """Split same-page KV pairs into size-bounded batches."""
        batches: List[List[Dict]] = []
        current_batch: List[Dict] = []
        current_tokens = 0

        for kv in kv_pairs:
            key = kv.get("key", "")
            value = kv.get("value", "")
            line = f"{key}: {value}" if key and value else f"{key}:"
            line_tokens = max(1, count_tokens(line))

            reached_pair_limit = len(current_batch) >= max_pairs
            reached_token_limit = (current_tokens + line_tokens) > max_tokens

            if current_batch and (reached_pair_limit or reached_token_limit):
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0

            current_batch.append(kv)
            current_tokens += line_tokens

        if current_batch:
            batches.append(current_batch)

        return batches

    def _merge_enriched_kv_bboxes(self, kv_pairs: List[Dict], page_num: int) -> Optional[Dict]:
        """Merge per-KV bboxes on a page into one representative bbox."""
        bboxes = []
        for kv in kv_pairs:
            bbox = kv.get("bbox")
            if isinstance(bbox, dict) and bbox.get("page") == page_num:
                bboxes.append(bbox)

        if not bboxes:
            return None

        return {
            "page": page_num,
            "x0": min(b["x0"] for b in bboxes),
            "y0": min(b["y0"] for b in bboxes),
            "x1": max(b["x1"] for b in bboxes),
            "y1": max(b["y1"] for b in bboxes),
        }

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


    def _build_chunk_text(
        self,
        section: SectionGroup,
        sequence: int,
        total: int
    ) -> str:
        """Build chunk text. Returns text only (use _build_chunk_text_with_pages for metadata)."""
        text, _ = self._build_chunk_text_with_pages(section)
        return text

    def _build_chunk_text_with_pages(
        self,
        section: SectionGroup,
    ) -> Tuple[str, List[Dict]]:
        """
        Build chunk text with [Page N] markers at page transitions, and collect
        paragraph_pages metadata for accurate citation and PDF highlighting.

        Returns:
            (text, paragraph_pages) where paragraph_pages is a list of:
              {"page": N, "char_offset": M, "bbox": {x0, y0, x1, y1}}
            one entry per page boundary within the chunk.
            For single-page chunks, returns a single entry with char_offset=0.
        """
        lines = []
        current_page: Optional[int] = None

        # paragraph_pages accumulates one entry per page seen.
        # {page -> {"char_offset": int, "bboxes": [...]}} — merged after building.
        page_info: Dict[int, Dict] = {}

        if section.section_heading:
            lines.append(section.section_heading)
            lines.append("")

        for para in section.paragraphs:
            content = para.get("content", "")
            if not content:
                continue

            para_page = self._get_paragraph_page(para)

            if para_page is not None and para_page != current_page:
                # Record the char offset where this page's content starts
                char_offset = len("\n".join(lines)) + (1 if lines else 0)
                if para_page not in page_info:
                    page_info[para_page] = {"char_offset": char_offset, "bboxes": []}
                # Insert [Page N] marker on transitions (not on the very first page)
                if current_page is not None:
                    lines.append(f"[Page {para_page}]")
                    # Recompute char_offset after inserting the marker line
                    page_info[para_page]["char_offset"] = len("\n".join(lines)) + 1
                current_page = para_page

            # Collect per-paragraph bbox for this page
            if para_page and para_page in page_info:
                for br in para.get("bounding_regions", []):
                    if br.get("page_number") == para_page:
                        polygon = br.get("polygon", [])
                        if len(polygon) == 8:
                            page_info[para_page]["bboxes"].append(
                                self._polygon_to_bbox(polygon)
                            )

            lines.append(content)

        text = "\n".join(lines)

        # Build final paragraph_pages list sorted by char_offset
        paragraph_pages = []
        for page, info in sorted(page_info.items(), key=lambda x: x[1]["char_offset"]):
            bboxes = info["bboxes"]
            merged_bbox = {
                "x0": min(b["x0"] for b in bboxes),
                "y0": min(b["y0"] for b in bboxes),
                "x1": max(b["x1"] for b in bboxes),
                "y1": max(b["y1"] for b in bboxes),
            } if bboxes else None
            paragraph_pages.append({
                "page": page,
                "char_offset": info["char_offset"],
                "bbox": merged_bbox,
            })

        return text, paragraph_pages

    def _get_paragraph_page(self, para: Dict) -> Optional[int]:
        """Return the page number of a paragraph from its first bounding region."""
        for br in para.get("bounding_regions", []):
            page_num = br.get("page_number")
            if page_num:
                return page_num
        return para.get("page_number")

    def _estimate_section_tokens(self, paragraphs: List[Dict]) -> int:
        """Estimate total tokens in a section."""
        total_chars = sum(len(p.get("content", "")) for p in paragraphs)
        return count_tokens(" " * total_chars)  # Rough estimate

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

    def _calculate_single_kv_bbox(self, kv: Dict) -> Optional[Dict]:
        """
        Calculate bounding box for a SINGLE key-value pair from its bounding regions.

        Prefers the VALUE bounding region so PDF highlights show where the actual
        data is, not the label. Falls back to merged key+value when no value region
        is available (e.g., Azure DI found key only).

        Args:
            kv: Single key-value pair with bounding_regions (and optionally
                key_bounding_regions / value_bounding_regions from the parser)

        Returns:
            Dict with {page, x0, y0, x1, y1} or None if no bounding regions
        """
        page_num = kv.get("page_number")
        if not page_num:
            return None

        def _regions_to_bbox(regions: list) -> Optional[Dict]:
            bboxes = []
            for br in regions:
                polygon = br.get("polygon", [])
                br_page = br.get("page_number")
                if len(polygon) == 8 and br_page == page_num:
                    bboxes.append(self._polygon_to_bbox(polygon))
            if not bboxes:
                return None
            return {
                "page": page_num,
                "x0": min(b["x0"] for b in bboxes),
                "y0": min(b["y0"] for b in bboxes),
                "x1": max(b["x1"] for b in bboxes),
                "y1": max(b["y1"] for b in bboxes)
            }

        # Prefer value regions (the data the user wants to verify)
        value_regions = kv.get("value_bounding_regions", [])
        if value_regions:
            result = _regions_to_bbox(value_regions)
            if result:
                return result

        # Fallback: merged key+value regions (backward compat / key-only KV pairs)
        bounding_regions = kv.get("bounding_regions", [])
        if not bounding_regions:
            return None
        return _regions_to_bbox(bounding_regions)

    def _calculate_kv_chunk_bbox(self, kv_pairs: List[Dict]) -> Optional[Dict]:
        """
        Calculate bounding box for a key-value chunk from KV pair bounding regions.

        Strategy:
        - Collect all bounding_regions from KV pairs
        - Convert polygons to bbox coordinates (x0, y0, x1, y1)
        - Merge into single bbox covering the entire chunk

        Args:
            kv_pairs: List of key-value pairs with bounding_regions

        Returns:
            Dict with {page, x0, y0, x1, y1} or None if no bounding regions
        """
        all_bboxes = []

        for kv in kv_pairs:
            bounding_regions = kv.get("bounding_regions", [])

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

        # Use the page of the first KV pair (chunks are same-page or consecutive)
        primary_page = kv_pairs[0].get("page_number")
        if not primary_page:
            return None

        # Filter bboxes for the primary page
        page_bboxes = [b for b in all_bboxes if b["page"] == primary_page]

        if not page_bboxes:
            return None

        # Calculate bounding box covering all KV pairs on primary page
        return {
            "page": primary_page,
            "x0": min(b["x0"] for b in page_bboxes),
            "y0": min(b["y0"] for b in page_bboxes),
            "x1": max(b["x1"] for b in page_bboxes),
            "y1": max(b["y1"] for b in page_bboxes)
        }

    def _calculate_paragraph_bbox(self, paragraphs: List[Dict]) -> Optional[Dict]:
        """
        Calculate bounding box for narrative paragraphs from their bounding regions.

        Strategy:
        - Collect all bounding_regions from paragraphs
        - Convert polygons to bbox coordinates (x0, y0, x1, y1)
        - Merge into single bbox covering the first page only (for PDF highlighting)

        Args:
            paragraphs: List of paragraph dicts with bounding_regions

        Returns:
            Dict with {page, x0, y0, x1, y1} or None if no bounding regions
        """
        all_bboxes = []
        first_page = None

        for para in paragraphs:
            bounding_regions = para.get("bounding_regions", [])

            for br in bounding_regions:
                polygon = br.get("polygon", [])
                page_num = br.get("page_number")

                if not polygon or len(polygon) < 8 or not page_num:
                    continue

                # Track first page for the overall bbox
                if first_page is None:
                    first_page = page_num

                # Only include bboxes from the first page (for highlighting)
                if page_num == first_page:
                    bbox = self._polygon_to_bbox(polygon)
                    all_bboxes.append(bbox)

        if not all_bboxes or first_page is None:
            return None

        # Merge all bboxes into one covering the entire paragraph group on first page
        return {
            "page": first_page,
            "x0": min(b["x0"] for b in all_bboxes),
            "y0": min(b["y0"] for b in all_bboxes),
            "x1": max(b["x1"] for b in all_bboxes),
            "y1": max(b["y1"] for b in all_bboxes)
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
