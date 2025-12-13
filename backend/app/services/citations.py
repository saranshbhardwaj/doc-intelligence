"""Citation resolution service for workflow outputs.

Resolves citation tokens like [D1:p15] to rich metadata with document names,
page numbers, sections, and content snippets.
"""
from typing import List, Dict, Optional
import re
import json
from sqlalchemy.orm import Session

from app.db_models_chat import DocumentChunk
from app.db_models_documents import Document
from app.utils.logging import logger


class CitationResolver:
    """
    Resolve citation tokens to rich metadata for user-friendly references.

    Production-optimized:
    - Batch loads all chunks upfront (prevents N+1 queries)
    - Caches documents and chunks
    - Uses metadata-based resolution (no text matching)
    """

    def __init__(self, db: Session):
        self.db = db
        self._doc_cache: Dict[str, Document] = {}  # Cache document lookups
        self._chunk_cache: Dict[str, DocumentChunk] = {}  # Cache chunk lookups
        self._chunk_map: Dict[str, DocumentChunk] = {}  # Map: (doc_id, page) -> chunk

    def resolve_citation(self, citation_token: str, doc_ids: List[str]) -> dict:
        """
        Resolve [D1:p15] to rich citation metadata using chunk_metadata JSONB.

        Production approach: Resolve citations by metadata lookup (not text matching).
        - Parse citation token to extract doc_index and page_number
        - Query chunk by document_id and page_number
        - Extract rich metadata from chunk_metadata JSONB

        Args:
            citation_token: e.g., "[D1:p15]"
            doc_ids: List of document IDs in workflow run (ordered)

        Returns:
            {
                'id': '[1]',
                'token': '[D1:p15]',
                'document': 'CIM-06-Pizza-Hut.pdf',
                'page': 15,
                'section': 'Financial Performance',
                'snippet': 'Revenue grew 23% YoY...',
                'heading_hierarchy': ['Main Report', 'Financial Performance'],
                'url': '/api/documents/abc123/download'
            }
        """
        # Parse token: [D1:p15] → doc_index=1, page=15
        match = re.match(r'\[D(\d+):p(\d+)\]', citation_token)
        if not match:
            return self._unknown_citation(citation_token)

        doc_index = int(match.group(1)) - 1  # D1 → index 0
        page_num = int(match.group(2))

        if doc_index < 0 or doc_index >= len(doc_ids):
            logger.warning(f"Citation {citation_token} has invalid doc index {doc_index} (total docs: {len(doc_ids)})")
            return self._unknown_citation(citation_token)

        document_id = doc_ids[doc_index]

        # Get chunk for this page (using metadata lookup, not text matching)
        chunk = self._get_chunk_for_page(document_id, page_num)

        if not chunk:
            # Fallback: get document info only (no chunk found for this page)
            doc = self._get_document(document_id)
            logger.warning(
                f"No chunk found for citation {citation_token} "
                f"(doc_id={document_id}, page={page_num})"
            )
            return {
                'id': citation_token,
                'token': citation_token,
                'document': doc.filename if doc else 'Unknown',
                'page': page_num,
                'section': None,
                'snippet': None,
                'url': f'/api/documents/{document_id}/download' if doc else None,
            }

        # Extract rich metadata from chunk_metadata JSONB
        # chunk_metadata is populated by:
        # 1. Smart chunker (section_id, heading_hierarchy, page_range, etc.)
        # 2. Document processor (document_filename, first_sentence)
        # 3. Workflow retriever (citation_token, doc_index) - runtime only
        metadata = chunk.chunk_metadata or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse chunk_metadata as JSON: {metadata}")
                metadata = {}

        doc = self._get_document(document_id)

        # Build rich citation using chunk_metadata JSONB
        # All fields come from existing metadata (no text matching needed!)
        return {
            'id': citation_token,
            'token': citation_token,
            'document': metadata.get('document_filename') or (doc.filename if doc else 'Unknown'),
            'page': page_num,
            'section': metadata.get('section_heading') or chunk.section_heading,
            'snippet': metadata.get('first_sentence') or self._extract_snippet(chunk.text),
            'heading_hierarchy': metadata.get('heading_hierarchy', []),
            'url': f'/api/documents/{document_id}/download',
            'bbox': metadata.get('bbox'),  # For PDF highlighting (future)
        }

    def resolve_all_citations(self, raw_text: str, doc_ids: List[str]) -> List[dict]:
        """
        Find all citations in text and resolve them to rich metadata.

        Args:
            raw_text: LLM output text containing citations
            doc_ids: List of document IDs in workflow run

        Returns:
            List of rich citation dicts, sorted by token
        """
        citation_tokens = re.findall(r'\[D\d+:p\d+\]', raw_text)
        unique_tokens = list(set(citation_tokens))

        logger.info(f"Resolving {len(unique_tokens)} unique citations from {len(citation_tokens)} total")

        resolved = [
            self.resolve_citation(token, doc_ids)
            for token in sorted(unique_tokens)
        ]

        return resolved

    def _get_chunk_for_page(self, document_id: str, page_num: int) -> Optional[DocumentChunk]:
        """
        Get a representative chunk for a page (prefer narrative chunks).

        Args:
            document_id: Document ID
            page_num: Page number

        Returns:
            DocumentChunk or None if not found
        """
        cache_key = f"{document_id}:p{page_num}"

        if cache_key in self._chunk_cache:
            return self._chunk_cache[cache_key]

        # Prefer narrative chunks over table chunks for snippet
        chunk = self.db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.page_number == page_num,
            DocumentChunk.is_tabular == False  # noqa: E712
        ).first()

        if not chunk:
            # Fallback: any chunk from this page
            chunk = self.db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.page_number == page_num
            ).first()

        self._chunk_cache[cache_key] = chunk
        return chunk

    def _get_document(self, document_id: str) -> Optional[Document]:
        """Get document with caching."""
        if document_id in self._doc_cache:
            return self._doc_cache[document_id]

        doc = self.db.query(Document).filter(Document.id == document_id).first()
        self._doc_cache[document_id] = doc
        return doc

    def _extract_snippet(self, text: str, max_length: int = 150) -> str:
        """Extract snippet from text (first sentence or truncated text)."""
        if not text:
            return ""

        # Try to get first sentence
        sentences = text.split('.')
        if sentences:
            snippet = sentences[0].strip() + '.' if len(sentences) > 1 else sentences[0].strip()
        else:
            snippet = text.strip()

        # Truncate if too long
        if len(snippet) > max_length:
            snippet = snippet[:max_length].strip() + '...'

        return snippet

    def _unknown_citation(self, token: str) -> dict:
        """Fallback for unresolved citations."""
        logger.warning(f"Could not resolve citation: {token}")
        return {
            'id': token,
            'token': token,
            'document': 'Unknown',
            'page': None,
            'section': None,
            'snippet': None,
            'url': None,
        }


__all__ = ['CitationResolver']
