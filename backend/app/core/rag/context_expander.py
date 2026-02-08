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
from app.core.rag.query_understanding import QueryType

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

    async def expand_with_batch(
        self,
        chunks: List[Dict],
        session: AsyncSession,
        max_expansion_per_chunk: int = 2,
        query_type: Optional[QueryType] = None
    ) -> List[Dict]:
        """
        Expand chunks with batch fetching (eliminates N+1 query problem).

        This method uses a two-pass approach:
        1. Collect all IDs to fetch
        2. Single batch query to fetch all needed chunks
        3. Build expanded list with light scoring

        Args:
            chunks: Retrieved chunks to expand
            session: AsyncSession for database queries
            max_expansion_per_chunk: Maximum additional chunks to add per original chunk
            query_type: Query type for adaptive expansion config

        Returns:
            Expanded list of chunks with _expansion_reason, _expanded_from, and rerank_score fields
        """
        # PASS 1: Collect all IDs to fetch
        expansion_ids = set()
        expansion_map = {}  # chunk_id -> [(target_id, reason, score_factor)]

        for chunk in chunks:
            chunk_id = chunk['id']
            metadata = chunk.get('chunk_metadata') or chunk.get('metadata') or {}
            expansion_map[chunk_id] = []

            config = self._get_expansion_config(chunk, query_type)

            # Tables need narrative
            if config['fetch_narrative'] and metadata.get('linked_narrative_id'):
                target_id = metadata['linked_narrative_id']
                expansion_ids.add(target_id)
                expansion_map[chunk_id].append((target_id, 'table_context', 0.90))

            # Narratives may need tables
            if config['fetch_tables'] and metadata.get('linked_table_ids'):
                for table_id in metadata['linked_table_ids'][:config['max_tables']]:
                    expansion_ids.add(table_id)
                    expansion_map[chunk_id].append((table_id, 'linked_table', 0.85))

            # Continuations need parent
            if config['fetch_parent'] and metadata.get('is_continuation') and metadata.get('parent_chunk_id'):
                parent_id = metadata['parent_chunk_id']
                expansion_ids.add(parent_id)
                expansion_map[chunk_id].append((parent_id, 'continuation_parent', 0.75))

        # PASS 2: Single batch fetch (1 query instead of N)
        if not expansion_ids:
            return chunks

        fetched_chunks = await self._batch_fetch_chunks(list(expansion_ids), session)

        # PASS 3: Build expanded list with light scoring
        expanded = []
        seen_ids = set()

        for chunk in chunks:
            expanded.append(chunk)
            seen_ids.add(chunk['id'])

            parent_score = chunk.get('rerank_score', chunk.get('hybrid_score', 1.0))

            for target_id, reason, score_factor in expansion_map.get(chunk['id'], []):
                if target_id in seen_ids or target_id not in fetched_chunks:
                    continue

                expanded_chunk = fetched_chunks[target_id].copy()
                expanded_chunk['_expansion_reason'] = reason
                expanded_chunk['_expanded_from'] = chunk['id']
                expanded_chunk['rerank_score'] = parent_score * score_factor
                expanded_chunk['_is_expanded'] = True

                expanded.append(expanded_chunk)
                seen_ids.add(target_id)

        logger.info(
            "Context expansion complete",
            extra={
                "original_count": len(chunks),
                "expanded_count": len(expanded),
                "added": len(expanded) - len(chunks),
                "query_type": query_type.value if query_type else None
            }
        )

        return expanded

    def _get_expansion_config(self, chunk: Dict, query_type: Optional[QueryType]) -> Dict:
        """
        Get expansion config based on query type.

        Args:
            chunk: Chunk to configure expansion for
            query_type: Query type for adaptive config

        Returns:
            Config dict with fetch_narrative, fetch_tables, fetch_parent, max_tables
        """
        is_tabular = chunk.get('is_tabular', False)

        configs = {
            QueryType.DATA_EXTRACTION: {
                'fetch_narrative': is_tabular,    # Tables always get narrative
                'fetch_tables': not is_tabular,   # Narratives get supporting tables
                'fetch_parent': True,
                'max_tables': 2
            },
            QueryType.SUMMARIZATION: {
                'fetch_narrative': False,
                'fetch_tables': False,
                'fetch_parent': True,  # Only continuations
                'max_tables': 0
            },
            QueryType.ENTITY_LOOKUP: {
                'fetch_narrative': is_tabular,  # Tables get context
                'fetch_tables': False,          # No extra tables
                'fetch_parent': False,
                'max_tables': 0
            },
            QueryType.GENERAL_QA: {
                'fetch_narrative': is_tabular,
                'fetch_tables': not is_tabular,
                'fetch_parent': True,
                'max_tables': 1
            },
            QueryType.COMPARISON: {
                'fetch_narrative': is_tabular,
                'fetch_tables': not is_tabular,
                'fetch_parent': True,
                'max_tables': 2
            }
        }

        return configs.get(query_type, configs[QueryType.GENERAL_QA])

    async def _batch_fetch_chunks(self, chunk_ids: List[str], session: AsyncSession) -> Dict[str, Dict]:
        """
        Single query for all expansion chunks (eliminates N+1 problem).

        Args:
            chunk_ids: List of chunk IDs to fetch
            session: AsyncSession for database query

        Returns:
            Dict mapping chunk_id to chunk dict
        """
        try:
            result = await session.execute(
                select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
            )
            chunks = result.scalars().all()

            return {
                str(c.id): {
                    'id': str(c.id),
                    'document_id': c.document_id,
                    'text': c.text,
                    'page_number': c.page_number,
                    'is_tabular': c.is_tabular,
                    'section_heading': c.section_heading,
                    'chunk_metadata': c.chunk_metadata or {},
                    'metadata': c.chunk_metadata or {},  # Alias for compatibility
                    'token_count': c.token_count
                }
                for c in chunks
            }
        except Exception as e:
            logger.warning(f"Failed to batch fetch {len(chunk_ids)} chunks: {e}")
            return {}

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
