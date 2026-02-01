"""
Context Expander: Expands retrieved chunks with related context using metadata relationships.

This module handles expanding document chunks with their related context (linked tables,
narratives, parent chunks) to ensure the LLM receives complete information for analysis.
"""

import logging
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db_models_chat import DocumentChunk

logger = logging.getLogger(__name__)


class ContextExpander:
    """
    Expands retrieved chunks with related context using metadata relationships.

    When retrieving chunks, some context is often fragmented:
    - Tables retrieved without their explanatory narrative
    - Text continuations without their parent content
    - Related tables/narratives that don't appear in top-K results

    This service uses the chunk metadata to automatically fetch related context,
    providing the LLM with more complete information.
    """

    async def expand(
        self,
        chunks: List[Dict],
        session: AsyncSession,
        max_expansion_per_chunk: int = 2
    ) -> List[Dict]:
        """
        Expand chunks with their related context.

        For each chunk, fetches:
        - linked_narrative_id: If chunk is tabular
        - linked_table_ids: If chunk is narrative
        - parent_chunk_id: If chunk is a continuation

        Args:
            chunks: Retrieved chunks to expand
            session: AsyncSession for database queries
            max_expansion_per_chunk: Maximum additional chunks to add per original chunk

        Returns:
            Expanded list of chunks with _expansion_reason and _expanded_from fields
        """
        expanded = []
        seen_ids = set()

        for chunk in chunks:
            # Add original chunk
            expanded.append(chunk)
            seen_ids.add(chunk['id'])

            metadata = chunk.get('metadata', {})
            expansion_count = 0

            # 1. Tables need narrative context
            if chunk.get('is_tabular') and metadata.get('linked_narrative_id'):
                narrative = await self._fetch_chunk(
                    metadata['linked_narrative_id'],
                    session
                )
                if narrative and narrative['id'] not in seen_ids:
                    narrative['_expansion_reason'] = 'table_context'
                    narrative['_expanded_from'] = chunk['id']
                    expanded.append(narrative)
                    seen_ids.add(narrative['id'])
                    expansion_count += 1
                    logger.debug(
                        f"Expanded table {chunk['id']} with narrative {narrative['id']}"
                    )

            # 2. Narratives mentioning data need tables
            if not chunk.get('is_tabular') and metadata.get('linked_table_ids'):
                remaining_slots = max_expansion_per_chunk - expansion_count
                for table_id in metadata['linked_table_ids'][:remaining_slots]:
                    table = await self._fetch_chunk(table_id, session)
                    if table and table['id'] not in seen_ids:
                        table['_expansion_reason'] = 'linked_table'
                        table['_expanded_from'] = chunk['id']
                        expanded.append(table)
                        seen_ids.add(table['id'])
                        expansion_count += 1
                        logger.debug(
                            f"Expanded narrative {chunk['id']} with table {table['id']}"
                        )

            # 3. Continuations need parent context
            if metadata.get('is_continuation') and metadata.get('parent_chunk_id'):
                if expansion_count < max_expansion_per_chunk:
                    parent = await self._fetch_chunk(
                        metadata['parent_chunk_id'],
                        session
                    )
                    if parent and parent['id'] not in seen_ids:
                        parent['_expansion_reason'] = 'continuation_parent'
                        parent['_expanded_from'] = chunk['id']
                        expanded.append(parent)
                        seen_ids.add(parent['id'])
                        logger.debug(
                            f"Expanded continuation {chunk['id']} with parent {parent['id']}"
                        )

        logger.info(
            f"Context expansion complete",
            extra={
                "original_count": len(chunks),
                "expanded_count": len(expanded),
                "added": len(expanded) - len(chunks)
            }
        )

        return expanded

    async def _fetch_chunk(
        self,
        chunk_id: str,
        session: AsyncSession
    ) -> Optional[Dict]:
        """
        Fetch a single chunk by ID from the database.

        Args:
            chunk_id: ID of chunk to fetch
            session: AsyncSession for database query

        Returns:
            Chunk dict with id, text, page_number, is_tabular, metadata
            Returns None if chunk not found
        """
        try:
            result = await session.execute(
                select(DocumentChunk).where(DocumentChunk.id == chunk_id)
            )
            chunk = result.scalar_one_or_none()
            if chunk:
                return {
                    'id': str(chunk.id),
                    'text': chunk.text,
                    'page_number': chunk.page_number,
                    'is_tabular': chunk.is_tabular,
                    'metadata': chunk.metadata or {}
                }
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch chunk {chunk_id}: {e}")
            return None
