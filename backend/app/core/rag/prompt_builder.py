"""Prompt Builder for RAG Chat.

Responsible solely for constructing the final prompt string given:
    - user message
    - retrieved document chunks
    - recent verbatim messages
    - optional conversation summary

Pure functions (no I/O / network); easy to unit test.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.rag.comparison_retriever import ComparisonContext
    from app.core.rag.fact_extractor import DocumentFacts
    from app.db_models import Document


class PromptBuilder:
    def __init__(self, prompt_version: str | None = None):
        from app.core.rag.prompts import get_rag_prompt_set
        self._prompts = get_rag_prompt_set(prompt_version)

    def format_conversation(self, recent_messages: List[Dict[str, Any]], summary_text: Optional[str]) -> str:
        sections: List[str] = []
        if summary_text:
            sections.append("=== CONVERSATION SUMMARY ===\n" + summary_text.strip() + "\n")
        if recent_messages:
            recent_lines = []
            for m in recent_messages:
                recent_lines.append(f"{m['role'].title()}: {m['content']}")
            sections.append("=== RECENT MESSAGES ===\n" + "\n".join(recent_lines) + "\n")
        return "\n".join(sections) if sections else "[No prior conversation]"

    def _format_chunks(
        self,
        relevant_chunks: List[Dict[str, Any]],
        doc_id_to_index: Optional[Dict[str, int]] = None,
    ) -> str:
        """Format retrieved chunks into a numbered source block for the LLM prompt.

        Each chunk is annotated with a [Dn:pN] citation hint so the LLM can
        reproduce the canonical citation format in its response.

        Args:
            relevant_chunks: Retrieved document chunks.
            doc_id_to_index: Mapping of document_id → D-number (1-based).
                             Built from the session's stable document_index.
                             If None, documents are assigned indices by first appearance.
        """
        context_sections: List[str] = []
        # Build a local first-appearance index as fallback when doc_id_to_index not provided
        _local_index: Dict[str, int] = {}

        for i, chunk in enumerate(relevant_chunks, 1):
            doc_id = str(chunk.get('document_id', ''))
            metadata = chunk.get('chunk_metadata') or {}

            # Determine source page label for the citation hint.
            # For multi-page chunks, paragraph_pages tracks which page each portion
            # of the text starts on. Show the full range so the LLM can use the
            # [Page N] markers embedded in the chunk text to cite accurately.
            paragraph_pages = metadata.get('paragraph_pages')
            if paragraph_pages and len(paragraph_pages) > 1:
                first_page = paragraph_pages[0]['page']
                last_page = paragraph_pages[-1]['page']
                page_label = f"{first_page}-{last_page}"
                # citation_hint uses the anchor (first) page; LLM refines via [Page N] markers
                citation_page = first_page
            else:
                bbox = metadata.get('bbox', {})
                citation_page = (bbox.get('page') if isinstance(bbox, dict) and bbox else None) or chunk.get('page_number', 1)
                page_label = str(citation_page)

            if doc_id_to_index is not None:
                d_num = doc_id_to_index.get(doc_id, 1)
            else:
                if doc_id not in _local_index:
                    _local_index[doc_id] = len(_local_index) + 1
                d_num = _local_index[doc_id]

            citation_hint = f"[D{d_num}:p{citation_page}]"
            source_info = f"Source {i}: {doc_id} (Page {page_label}) {citation_hint}"
            if chunk.get('section_heading'):
                source_info += f" - {chunk['section_heading']}"
            context_sections.append(f"{source_info}\n{chunk['text']}\n")
        return "\n---\n\n".join(context_sections)

    def build(
        self,
        user_message: str,
        relevant_chunks: List[Dict[str, Any]],
        recent_messages: List[Dict[str, Any]],
        summary_text: Optional[str] = None,
        doc_id_to_index: Optional[Dict[str, int]] = None,
    ) -> str:
        if not relevant_chunks:
            convo_sections = self.format_conversation(recent_messages, summary_text)
            return (
                f"{self._prompts.system_instructions_no_chunks}\n"
                f"CONVERSATION CONTEXT:\n{convo_sections}\n\n"
                "DOCUMENT EXCERPTS:\n\n[No relevant document excerpts found for this query]\n\n---\n\n"
                f"USER QUESTION: {user_message}\n\nANSWER:" )

        context = self._format_chunks(relevant_chunks, doc_id_to_index=doc_id_to_index)
        convo_sections = self.format_conversation(recent_messages, summary_text)
        return (
            f"{self._prompts.system_instructions_with_chunks}\n"
            f"CONVERSATION CONTEXT:\n{convo_sections}\n\n"
            "DOCUMENT EXCERPTS:\n\n"
            f"{context}\n\n---\n\n"
            f"USER QUESTION: {user_message}\n\nANSWER:" )

    def build_split(
        self,
        user_message: str,
        relevant_chunks: List[Dict[str, Any]],
        recent_messages: List[Dict[str, Any]],
        summary_text: Optional[str] = None,
        doc_id_to_index: Optional[Dict[str, int]] = None,
        include_history: bool = True,
    ) -> tuple:
        """
        Return (system_prompt, user_content) for Anthropic prompt caching.

        System prompt (stable between compaction points — cached by Anthropic):
          - Role instructions
          - Conversation summary (if any, only when include_history=True)

        User content (changes every turn — not cached):
          - Recent verbatim messages (only when include_history=True)
          - Document chunks
          - User question

        The system prompt is marked with cache_control: ephemeral by the LLM client,
        giving a 5-minute cache TTL. Between compaction points the system prompt is
        byte-identical → cache hits → ~10x cheaper input token cost.

        When include_history=False (standalone questions), the system prompt contains
        only the instructions — identical across ALL sessions → maximum cache hit rate.
        """
        # --- System prompt (cached) ---
        instructions = (
            self._prompts.system_instructions_with_chunks
            if relevant_chunks
            else self._prompts.system_instructions_no_chunks
        )
        system_parts = [instructions]
        if include_history and summary_text:
            system_parts.append(f"\n=== CONVERSATION SUMMARY ===\n{summary_text.strip()}")
        system_prompt = "\n".join(system_parts)

        # --- User content (dynamic, not cached) ---
        recent_section = ""
        if include_history and recent_messages:
            lines = [f"{m['role'].title()}: {m['content']}" for m in recent_messages]
            recent_section = "=== RECENT MESSAGES ===\n" + "\n".join(lines) + "\n\n"

        if relevant_chunks:
            context = self._format_chunks(relevant_chunks, doc_id_to_index=doc_id_to_index)
            user_content = (
                f"{recent_section}"
                f"DOCUMENT EXCERPTS:\n\n{context}\n\n---\n\n"
                f"USER QUESTION: {user_message}\n\nANSWER:"
            )
        else:
            user_content = (
                f"{recent_section}"
                "DOCUMENT EXCERPTS:\n\n[No relevant document excerpts found for this query]\n\n---\n\n"
                f"USER QUESTION: {user_message}\n\nANSWER:"
            )

        return system_prompt, user_content

    def build_comparison_prompt(
        self,
        user_message: str,
        comparison_context: 'ComparisonContext',
        recent_messages: List[Dict[str, Any]],
        summary_text: Optional[str] = None,
        max_pairs: int = 8
    ) -> str:
        """
        Build prompt for document comparison with paired/clustered chunks.

        Handles both 2-document (paired) and 3+ document (clustered) comparisons.

        Args:
            user_message: User's comparison question
            comparison_context: ComparisonContext with paired or clustered chunks
            recent_messages: Recent conversation messages
            summary_text: Optional conversation summary
            max_pairs: Maximum number of pairs/clusters to include (default: 8)

        Returns:
            Formatted comparison prompt
        """
        from app.core.rag.comparison_retriever import ComparisonContext

        if not comparison_context.documents or len(comparison_context.documents) < 2:
            # Fallback to standard prompt if comparison context invalid
            return self.build(user_message, [], recent_messages, summary_text)

        num_docs = comparison_context.num_documents
        docs = comparison_context.documents

        # Build document headers
        prompt_parts = [
            self._prompts.comparison_system_instructions,
            "\n## Documents Being Compared\n",
        ]

        # List all documents with labels
        doc_labels = ['A', 'B', 'C']  # Support up to 3 documents
        for i, doc in enumerate(docs):
            label = doc_labels[i] if i < len(doc_labels) else str(i+1)
            prompt_parts.append(f"**Document {label}:** {doc.filename}\n")

        # Add conversation context if present
        convo_sections = self.format_conversation(recent_messages, summary_text)
        if convo_sections and convo_sections != "[No prior conversation]":
            prompt_parts.append(f"\nCONVERSATION CONTEXT:\n{convo_sections}\n")

        # Add paired or clustered content
        if num_docs == 2 and comparison_context.paired_chunks:
            # 2-document comparison: Use paired chunks
            prompt_parts.append("\n## Paired Content (Related Sections)\n")

            for i, pair in enumerate(comparison_context.paired_chunks[:max_pairs], 1):
                prompt_parts.append(f"\n### Comparison Point {i}: {pair.topic}\n")

                # Document A chunk
                page_a = pair.chunk_a.get('page_number', '?')
                prompt_parts.append(f"**From {docs[0].filename} (Page {page_a}) [D1:p{page_a}]:**\n")
                prompt_parts.append(f"{pair.chunk_a.get('text', '')}\n")

                # Document B chunk
                page_b = pair.chunk_b.get('page_number', '?')
                prompt_parts.append(f"**From {docs[1].filename} (Page {page_b}) [D2:p{page_b}]:**\n")
                prompt_parts.append(f"{pair.chunk_b.get('text', '')}\n")

        elif num_docs >= 3 and comparison_context.clustered_chunks:
            # 3+ document comparison: Use clustered chunks
            prompt_parts.append(f"\n## Clustered Content (Related Sections Across {num_docs} Documents)\n")

            for i, cluster in enumerate(comparison_context.clustered_chunks[:max_pairs], 1):
                prompt_parts.append(f"\n### Comparison Point {i}: {cluster.topic}\n")

                # Add chunk from each document in cluster
                for doc_idx, doc in enumerate(docs):
                    chunk = cluster.chunks.get(doc.id)

                    if chunk:
                        page = chunk.get('page_number', '?')
                        prompt_parts.append(f"**From {doc.filename} (Page {page}) [D{doc_idx+1}:p{page}]:**\n")
                        prompt_parts.append(f"{chunk.get('text', '')}\n")
                    else:
                        prompt_parts.append(f"**From {doc.filename}:** [No corresponding content found]\n")

        else:
            prompt_parts.append("\n[No semantically paired/clustered content found. Documents may cover different topics.]\n")

        # Add user question and output instructions
        prompt_parts.append("\n" + "="*80 + "\n")
        prompt_parts.append(f"USER QUESTION: {user_message}\n")
        prompt_parts.append("="*80 + "\n\n")
        prompt_parts.append("Generate your comparison with:\n")

        if num_docs == 2:
            prompt_parts.append("1. A markdown comparison table (3-8 rows) with Difference column\n")
            prompt_parts.append("2. 2-3 paragraphs analyzing the key differences\n")
            prompt_parts.append("3. Clear recommendation or conclusion\n\n")
            prompt_parts.append("Every claim must have a citation [D1:pN] or [D2:pN].\n\n")
        else:
            prompt_parts.append(f"1. A markdown comparison table (3-8 rows) with {num_docs} columns\n")
            prompt_parts.append(f"2. 2-3 paragraphs analyzing patterns and outliers across {num_docs} documents\n")
            prompt_parts.append("3. Clear recommendation highlighting best/worst options\n\n")
            prompt_parts.append(f"Every claim must have a citation [D1:pN], [D2:pN], [D3:pN], etc.\n\n")

        prompt_parts.append("ANSWER:\n")

        return "".join(prompt_parts)

    def build_fact_based_comparison_prompt(
        self,
        docs: List["Document"],
        document_facts: List["DocumentFacts"],
        user_message: str,
        comparison_aspects: List[str],
        recent_messages: List[Dict[str, Any]],
        summary_text: Optional[str] = None
    ) -> str:
        """
        Build comparison prompt from extracted facts.

        This approach uses extracted facts instead of raw chunks, providing:
        - Cleaner, more structured input to the LLM
        - Better handling of poorly formatted documents
        - Improved accuracy on multi-document comparisons

        Args:
            docs: Documents being compared
            document_facts: Extracted facts from each document
            user_message: User's comparison question
            comparison_aspects: Aspects to compare (from QueryUnderstanding)
            recent_messages: Recent conversation messages
            summary_text: Optional conversation summary

        Returns:
            Formatted comparison prompt ready for LLM
        """
        prompt_parts = [
            self._prompts.comparison_system_instructions,
            "\n## Documents Being Compared\n",
        ]

        # List all documents with labels
        doc_labels = ['A', 'B', 'C', 'D', 'E']  # Support up to 5 documents
        for i, doc in enumerate(docs):
            label = doc_labels[i] if i < len(doc_labels) else str(i+1)
            prompt_parts.append(f"- **Document {label}**: {doc.filename}\n")

        # Add conversation context if present
        convo_sections = self.format_conversation(recent_messages, summary_text)
        if convo_sections and convo_sections != "[No prior conversation]":
            prompt_parts.append(f"\nCONVERSATION CONTEXT:\n{convo_sections}\n")

        # Add extracted facts by document
        prompt_parts.append("\n## Extracted Facts by Document\n")

        for i, facts in enumerate(document_facts):
            label = doc_labels[i] if i < len(doc_labels) else str(i+1)
            prompt_parts.append(f"\n### Document {label}: {facts.document_name}\n")

            if facts.facts:
                for fact in facts.facts:
                    # Format: fact_statement [D{i}:p{page}]
                    prompt_parts.append(
                        f"- {fact.fact} [D{i+1}:p{fact.source_page}]\n"
                    )
            else:
                prompt_parts.append("- [No specific facts extracted]\n")

        # Add comparison focus if specified
        if comparison_aspects:
            prompt_parts.append("\n## Comparison Focus\n")
            aspects_text = ", ".join(comparison_aspects)
            prompt_parts.append(f"Compare the following aspects: {aspects_text}\n")
        else:
            prompt_parts.append("\n## Comparison Focus\n")
            prompt_parts.append("Perform a comprehensive comparison across all dimensions\n")

        # Add user question and output instructions
        prompt_parts.append("\n" + "="*80 + "\n")
        prompt_parts.append(f"USER QUESTION: {user_message}\n")
        prompt_parts.append("="*80 + "\n\n")

        num_docs = len(docs)
        prompt_parts.append("Generate your comparison with:\n")

        if num_docs == 2:
            prompt_parts.append("1. A markdown comparison table with Difference column\n")
            prompt_parts.append("2. 2-3 paragraphs analyzing the key differences\n")
            prompt_parts.append("3. Clear recommendation or conclusion\n\n")
            prompt_parts.append("Every claim must have a citation [D1:pN] or [D2:pN].\n\n")
        else:
            prompt_parts.append(f"1. A markdown comparison table with {num_docs} document columns\n")
            prompt_parts.append(f"2. 2-3 paragraphs analyzing patterns and outliers across {num_docs} documents\n")
            prompt_parts.append("3. Clear recommendation highlighting best/worst options\n\n")
            doc_citations = ", ".join([f"[D{i+1}:pN]" for i in range(num_docs)])
            prompt_parts.append(f"Every claim must have a citation: {doc_citations}\n\n")

        prompt_parts.append("ANSWER:\n")

        return "".join(prompt_parts)
