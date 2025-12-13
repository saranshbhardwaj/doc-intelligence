"""Section Summary Prompt for Workflow Map-Reduce Execution

This prompt is used for NARRATIVE-ONLY summarization in map-reduce workflows.
Tables are NOT summarized - they pass through as full text for maximum fidelity.

Purpose:
- Compress narrative chunks from ~5K tokens → ~500 tokens (7-10x compression)
- Preserve all citations in document-token form
- Maintain factual accuracy without inference
- Output structured summary for synthesis
- High-density summaries to offset full table inclusion

Caching:
- This template is static and cacheable via Anthropic prompt caching
- Only the context chunks change between calls
- Saves ~90% cost on calls 2-N in a workflow
"""

import re
from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)

# Cacheable prompt template (100% static - no section-specific text)
# This gets cached by Anthropic and reused across ALL sections and workflows
WORKFLOW_SECTION_SUMMARY_PROMPT_CACHEABLE = """Compress narrative chunks into concise summaries with citations.

**Core Task:**
Create a compressed summary (target: 300-600 tokens from ~3-5K token input).
Preserve all numbers and citations exactly as they appear.

**Citation Format:**
Keep citations exactly as written: "[D1:p2]", "[D3:p5]", etc.
Include citations inline with facts: "Revenue: $111.9M [D1:p2]"

**Compression Strategy:**
- Remove verbose descriptions, keep facts and numbers
- Example: "Revenue grew significantly from $87.3M to $102.5M" → "Revenue: $87.3M → $102.5M [D1:p2]"
- Focus on quantitative data over qualitative descriptions
- Tables are preserved separately, so narrative can be maximally compressed

**CRITICAL JSON FORMATTING RULES:**
1. The "summary" field MUST be a single-line JSON string
2. DO NOT include actual line breaks or newlines in the summary field
3. Keep summary as a continuous paragraph with inline citations
4. If you need to separate points, use " | " (pipe) as separator, NOT newlines

**OUTPUT FORMAT (single-line summary field):**
Return valid JSON only (no preamble):

{
  "section_key": "<section_identifier>",
  "summary": "Terse summary paragraph with inline citations [D1:p2]. Additional facts [D3:p5]. Key metrics: Revenue $111.9M [D1:p2], EBITDA $25M [D1:p3].",
  "citations": ["[D1:p2]", "[D3:p5]", "[D1:p3]"],
  "key_metrics": [
    {"metric": "Revenue 2023", "value": "$111.9M", "citation": "[D1:p2]"}
  ]
}

IMPORTANT: Keep the summary as ONE continuous string. DO NOT use line breaks inside the summary field.

START YOUR RESPONSE WITH { IMMEDIATELY.
"""


# Table extraction prompt (cacheable)
# Extracts structured key metrics from any type of table
WORKFLOW_TABLE_EXTRACTION_PROMPT_CACHEABLE = """Extract key data points and metrics from table chunks as structured information.

**Your Task:**
1. Identify the most important data points, values, and metrics from tables
2. Extract them as structured key-value pairs with citations
3. Preserve ALL citations in exact document-token form (e.g., "[D1:p2]", "[D3:p5]")
4. Handle any table type: financial data, customer data, product specs, transaction history, etc.
5. Focus on decision-relevant information (not every cell, just key insights)
6. Target: 10-20 key metrics per table (prioritize most important)

**CRITICAL CITATION RULES:**
- Every metric MUST include its original citation from the table chunk
- Use exact citation format: "[D1:p2]" where D1 = Document 1, p2 = Page 2
- Do NOT drop, renumber, or modify citations

**OUTPUT FORMAT:**
Return valid JSON only (no preamble, no code fences):

{
  "section_key": "<section_identifier>",
  "key_metrics": [
    {
      "metric": "Revenue 2023",
      "value": "$111.9M",
      "citation": "[D1:p2]"
    },
    {
      "metric": "EBITDA Margin",
      "value": "22.3%",
      "citation": "[D1:p2]"
    },
    {
      "metric": "Total Stores",
      "value": "1,153",
      "citation": "[D1:p26]"
    }
  ],
  "citations": ["[D1:p2]", "[D1:p26]"],
  "table_count": 3
}

**Guidelines:**
- Metric names should be descriptive and specific (include year, category, etc.)
- Preserve exact values with units ($M, $B, %, x, etc.)
- Prioritize quantitative data over descriptive text
- If a table has multiple rows, extract representative or summary values
- Focus on metrics relevant to the section focus areas
- Extract metadata if useful (e.g., "Total Rows: 50", "Time Period: 2020-2023")

START YOUR RESPONSE WITH { IMMEDIATELY. No preamble text.
"""


def build_narrative_summary_prompt(
    section_spec: Dict,
    narrative_chunks: List[Dict],
    section_key: str
) -> dict:
    """
    Build separate system prompt (cacheable) and user message (dynamic).

    Args:
        section_spec: Section specification from retrieval spec
        narrative_chunks: Narrative chunks only (is_tabular=False)
        section_key: Section identifier (e.g., "financial_performance")

    Returns:
        Dict with:
            - system_prompt: Static instructions (100% cacheable)
            - user_message: Section info + chunks (dynamic)
    """
    section_title = section_spec.get("title", section_key.replace("_", " ").title())
    queries = section_spec.get("queries", [])
    queries_text = ", ".join(queries[:5])  # First 5 queries as focus

    # Static system prompt (cached)
    system_prompt = WORKFLOW_SECTION_SUMMARY_PROMPT_CACHEABLE

    # Build dynamic user message
    user_message_parts = [
        f"SECTION: {section_title}",
        f"SECTION KEY: {section_key}",
        f"FOCUS AREAS: {queries_text}",
        f"",
        f"NARRATIVE CHUNKS TO SUMMARIZE:",
        f""
    ]

    # Add chunks with citation prefixes (same as direct execution)
    for i, chunk in enumerate(narrative_chunks):
        citation = chunk.get("citation", "[?]")  # Added by workflow_retriever
        chunk_text = chunk.get("text", "")
        page_num = chunk.get("page_number", 0)
        doc_id = chunk.get("document_id", "unknown")
        section_heading = chunk.get("section_heading", "")

        # Format with citation prefix so LLM can preserve citations
        formatted_text = f"{citation} {chunk_text}"

        user_message_parts.append(
            f"--- Narrative Chunk {i+1} ---\n"
            f"Document: {doc_id}, Page: {page_num}\n"
            f"Section: {section_heading}\n\n"
            f"{formatted_text}\n"
        )

    user_message = "\n".join(user_message_parts)

    return {
        "system_prompt": system_prompt,
        "user_message": user_message
    }


def build_table_extraction_prompt(
    section_spec: Dict,
    table_chunks: List[Dict],
    section_key: str
) -> dict:
    """
    Build separate system prompt (cacheable) and user message (dynamic) for table extraction.

    Args:
        section_spec: Section specification from retrieval spec
        table_chunks: Table chunks only (is_tabular=True)
        section_key: Section identifier (e.g., "financial_performance")

    Returns:
        Dict with:
            - system_prompt: Static instructions (100% cacheable)
            - user_message: Section info + table chunks (dynamic)
    """
    section_title = section_spec.get("title", section_key.replace("_", " ").title())
    queries = section_spec.get("queries", [])
    queries_text = ", ".join(queries[:5])  # First 5 queries as focus

    # Static system prompt (cached)
    system_prompt = WORKFLOW_TABLE_EXTRACTION_PROMPT_CACHEABLE

    # Build dynamic user message
    user_message_parts = [
        f"SECTION: {section_title}",
        f"SECTION KEY: {section_key}",
        f"FOCUS AREAS: {queries_text}",
        f"",
        f"TABLE CHUNKS TO EXTRACT KEY METRICS FROM:",
        f""
    ]

    # Add table chunks with citation prefixes
    for i, chunk in enumerate(table_chunks):
        citation = chunk.get("citation", "[?]")  # Added by workflow_retriever
        chunk_text = chunk.get("text", "")
        page_num = chunk.get("page_number", 0)
        doc_id = chunk.get("document_id", "unknown")
        section_heading = chunk.get("section_heading", "")

        # Format with citation prefix so LLM can preserve citations
        formatted_text = f"{citation} {chunk_text}"

        user_message_parts.append(
            f"--- Table Chunk {i+1} ---\n"
            f"Document: {doc_id}, Page: {page_num}\n"
            f"Section: {section_heading}\n\n"
            f"{formatted_text}\n"
        )

    user_message = "\n".join(user_message_parts)

    return {
        "system_prompt": system_prompt,
        "user_message": user_message
    }


def validate_citations_preserved(
    input_chunks: List[Dict],
    summary_result: Dict,
    section_key: str,
    run_id: str
) -> Dict[str, any]:
    """
    Validate that citations from input chunks are preserved in summary.

    Args:
        input_chunks: Original chunks with citations
        summary_result: LLM summary response
        section_key: Section identifier
        run_id: Workflow run ID for logging

    Returns:
        Validation result dict with warnings
    """
    # Extract all citations from input chunks
    # NOTE: Citations are in chunk["citation"] field (added by workflow_retriever)
    # NOT in chunk["text"] (text is clean, no markup)
    input_citations: Set[str] = set()
    citation_pattern = r'\[D\d+:p\d+\]'

    for chunk in input_chunks:
        # Get citation from field (NOT from text)
        citation = chunk.get("citation", "")
        if citation and re.match(citation_pattern, citation):
            input_citations.add(citation)

    # Extract citations from summary
    summary_text = summary_result.get("summary", "")
    output_citations_in_text = set(re.findall(citation_pattern, summary_text))
    output_citations_array = set(summary_result.get("citations", []))

    # Combine citations from both summary text and citations array
    output_citations = output_citations_in_text | output_citations_array

    # Check for citation loss
    dropped_citations = input_citations - output_citations
    validation_result = {
        "input_citation_count": len(input_citations),
        "output_citation_count": len(output_citations),
        "citations_preserved": len(dropped_citations) == 0,
        "dropped_citations": list(dropped_citations),
        "warnings": []
    }

    if dropped_citations:
        warning = (
            f"Citation loss in section '{section_key}': "
            f"{len(input_citations)} → {len(output_citations)} citations. "
            f"Dropped: {dropped_citations}"
        )
        validation_result["warnings"].append(warning)
        logger.warning(
            warning,
            extra={
                "run_id": run_id,
                "section_key": section_key,
                "dropped_citations": list(dropped_citations)
            }
        )

    # Check that citations array matches citations in text
    if output_citations_in_text != output_citations_array:
        missing_in_array = output_citations_in_text - output_citations_array
        if missing_in_array:
            warning = f"Citations in summary text not in citations array: {missing_in_array}"
            validation_result["warnings"].append(warning)
            logger.warning(
                warning,
                extra={"run_id": run_id, "section_key": section_key}
            )

    logger.info(
        f"Citation validation for section '{section_key}': "
        f"{len(input_citations)} input → {len(output_citations)} output, "
        f"preserved={validation_result['citations_preserved']}",
        extra={
            "run_id": run_id,
            "section_key": section_key,
            "validation_result": validation_result
        }
    )

    return validation_result
