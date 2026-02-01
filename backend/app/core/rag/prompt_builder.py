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
    SYSTEM_INSTRUCTIONS_NO_CHUNKS = (
        "You are a financial analyst AI assistant. Answer the user's question based on the provided document excerpts and prior conversation.\n\n"
        "IMPORTANT INSTRUCTIONS:\n"
        "- Only use information from the provided document excerpts\n"
        "- If there are no relevant excerpts, say you don't have enough evidence and ask a brief follow-up\n"
        "- If the documents don't contain relevant information, say so clearly\n"
        "- Be concise but thorough\n"
    )

    SYSTEM_INSTRUCTIONS_WITH_CHUNKS = (
        "You are a financial analyst AI assistant. Answer the user's question based on the provided document excerpts and prior conversation.\n\n"
        "IMPORTANT INSTRUCTIONS:\n"
        "- Only use information from the provided document excerpts\n"
        "- If the documents don't contain relevant information, say so clearly\n"
        "- If evidence is insufficient, say so and ask a brief follow-up\n"
        "- Cite sources using the format [D1:pN] where D1 is the document number and N is the page number\n"
        "  Example: \"Revenue increased by 15% [D1:p5] compared to prior quarter.\"\n"
        "- Every factual claim should include a citation\n"
        "- Be concise but thorough\n"
        "- Use bullet points for clarity when appropriate\n"
    )

    COMPARISON_SYSTEM_INSTRUCTIONS = (
        "You are a financial analyst AI assistant comparing multiple documents.\n\n"
        "TASK: Compare the documents based on the user's question.\n\n"
        "OUTPUT FORMAT:\n"
        "1. Start with a comparison table (markdown) showing key metrics side-by-side\n"
        "2. Follow with 2-3 paragraphs analyzing the most important differences\n"
        "3. Provide a clear conclusion or recommendation if appropriate\n\n"
        "COMPARISON TABLE FORMAT (2 documents):\n"
        "| Metric | Document A | Document B | Difference |\n"
        "|--------|------------|------------|------------|\n"
        "| Cap Rate | 6.2% [D1:p5] | 5.8% [D2:p3] | +0.4% |\n\n"
        "COMPARISON TABLE FORMAT (3+ documents):\n"
        "| Metric | Document A | Document B | Document C |\n"
        "|--------|------------|------------|------------|\n"
        "| Cap Rate | 6.2% [D1:p5] | 5.8% [D2:p3] | 5.5% [D3:p7] |\n\n"
        "CITATION FORMAT:\n"
        "- Use [D1:pN] for Document 1 citations\n"
        "- Use [D2:pN] for Document 2 citations\n"
        "- Use [D3:pN] for Document 3 citations (if comparing 3 documents)\n\n"
        "IMPORTANT:\n"
        "- Be specific with numbers and metrics\n"
        "- Highlight material differences across ALL documents\n"
        "- Only use information from the provided paired/clustered content\n"
        "- Every quantitative claim must have a citation\n"
        "- For 3+ documents, identify patterns and outliers\n"
    )

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

    def build(
        self,
        user_message: str,
        relevant_chunks: List[Dict[str, Any]],
        recent_messages: List[Dict[str, Any]],
        summary_text: Optional[str] = None
    ) -> str:
        if not relevant_chunks:
            convo_sections = self.format_conversation(recent_messages, summary_text)
            return (
                f"{self.SYSTEM_INSTRUCTIONS_NO_CHUNKS}\n"
                f"CONVERSATION CONTEXT:\n{convo_sections}\n\n"
                "DOCUMENT EXCERPTS:\n\n[No relevant document excerpts found for this query]\n\n---\n\n"
                f"USER QUESTION: {user_message}\n\nANSWER:" )

        context_sections: List[str] = []
        for i, chunk in enumerate(relevant_chunks, 1):
            source_info = f"Source {i}: {chunk['document_id']}"
            if chunk.get('page_number'):
                source_info += f" (Page {chunk['page_number']})"
            if chunk.get('section_heading'):
                source_info += f" - {chunk['section_heading']}"
            context_sections.append(f"{source_info}\n{chunk['text']}\n")

        context = "\n---\n\n".join(context_sections)
        convo_sections = self.format_conversation(recent_messages, summary_text)
        return (
            f"{self.SYSTEM_INSTRUCTIONS_WITH_CHUNKS}\n"
            f"CONVERSATION CONTEXT:\n{convo_sections}\n\n"
            "DOCUMENT EXCERPTS:\n\n"
            f"{context}\n\n---\n\n"
            f"USER QUESTION: {user_message}\n\nANSWER:" )

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
            self.COMPARISON_SYSTEM_INSTRUCTIONS,
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
            self.COMPARISON_SYSTEM_INSTRUCTIONS,
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
