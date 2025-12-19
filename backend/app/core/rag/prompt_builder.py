"""Prompt Builder for RAG Chat.

Responsible solely for constructing the final prompt string given:
    - user message
    - retrieved document chunks
    - recent verbatim messages
    - optional conversation summary

Pure functions (no I/O / network); easy to unit test.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional


class PromptBuilder:
    SYSTEM_INSTRUCTIONS_NO_CHUNKS = (
        "You are a financial analyst AI assistant. Answer the user's question based on the provided document excerpts and prior conversation.\n\n"
        "IMPORTANT INSTRUCTIONS:\n"
        "- Only use information from the provided document excerpts\n"
        "- If the documents don't contain relevant information, say so clearly\n"
        "- Be concise but thorough\n"
    )

    SYSTEM_INSTRUCTIONS_WITH_CHUNKS = (
        "You are a financial analyst AI assistant. Answer the user's question based on the provided document excerpts and prior conversation.\n\n"
        "IMPORTANT INSTRUCTIONS:\n"
        "- Only use information from the provided document excerpts\n"
        "- If the documents don't contain relevant information, say so clearly\n"
        "- Cite sources by mentioning the document name and page number\n"
        "- Be concise but thorough\n"
        "- Use bullet points for clarity when appropriate\n"
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
