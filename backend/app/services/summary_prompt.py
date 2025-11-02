"""Prompts for cheap LLM summarization of document chunks.

This is used to condense narrative text before sending to expensive LLM for structured extraction.
Tables are NOT summarized - they're sent raw to preserve exact numbers.
"""

SUMMARY_SYSTEM_PROMPT = """You are a financial analyst assistant specializing in document summarization.

Your job is to create concise, factual summaries of document sections while preserving ALL critical information.

CRITICAL RULES:
1. Preserve ALL numbers EXACTLY as written (revenues, costs, percentages, ratios, multiples, etc.)
2. Preserve ALL dates, years, and time periods
3. Preserve ALL company names, people names, locations, and proper nouns
4. Preserve ALL key business facts (products, services, customers, operations, strategy)
5. Remove marketing fluff, redundant language, and generic statements
6. Keep summaries factual and concise (2-4 sentences per section)
7. If the section is mostly generic boilerplate, say "Boilerplate section - no key facts"

OUTPUT FORMAT:
- Return only the summary text
- Use bullet points for lists of facts
- Always end with "Key Numbers:" followed by all numbers found (if any)
- If no numbers found, omit the "Key Numbers:" line

DO NOT:
- Add your own analysis or opinions
- Round or approximate numbers (preserve exact values)
- Skip important details to save space
- Add information not in the source text
"""


SUMMARY_USER_PROMPT_TEMPLATE = """Summarize the following document section. Preserve all numbers and key facts.

SECTION TEXT:
{chunk_text}

Summary (2-4 sentences):"""


BATCH_SUMMARY_PROMPT_TEMPLATE = """Summarize each page section below. Preserve ALL numbers and key facts.

{batch_text}

Provide a summary for each page in this format:

Page [N]: [2-4 sentence summary]
Key Numbers: [list all numbers found]

Page [N+1]: [2-4 sentence summary]
Key Numbers: [list all numbers found]

Summaries:"""


def create_summary_prompt(chunk_text: str) -> str:
    """Generate prompt for summarizing a single chunk."""
    return SUMMARY_USER_PROMPT_TEMPLATE.format(chunk_text=chunk_text)


def create_batch_summary_prompt(chunks: list[dict]) -> str:
    """Generate prompt for summarizing multiple chunks in one call.

    Args:
        chunks: List of dicts with 'page' and 'text' keys

    Returns:
        Formatted prompt string
    """
    batch_sections = []
    for chunk in chunks:
        page_num = chunk.get("page", "?")
        text = chunk.get("text", "")
        batch_sections.append(f"[Page {page_num}]\n{text}")

    batch_text = "\n\n---PAGE BREAK---\n\n".join(batch_sections)
    return BATCH_SUMMARY_PROMPT_TEMPLATE.format(batch_text=batch_text)


# Example usage for testing
if __name__ == "__main__":
    example_chunk = """
    Pizza Hut Holdings operates over 450 franchise locations across the Western United States.
    The company has experienced strong growth, with revenue increasing from $87.3M in 2021 to
    $102.5M in 2022, representing a 17.4% year-over-year increase. The company's EBITDA margin
    has remained stable at approximately 22-23% over this period. Management believes the business
    is well-positioned to continue expanding through both organic growth and strategic acquisitions
    in adjacent markets. The company has a proven track record of delivering exceptional value to
    its franchise partners and maintains strong relationships with suppliers.
    """

    prompt = create_summary_prompt(example_chunk)
    print("SINGLE CHUNK PROMPT:")
    print("=" * 60)
    print(prompt)
    print("\n")

    # Expected output from cheap LLM:
    expected = """Pizza Hut Holdings operates 450+ franchise locations in Western US. Revenue grew from $87.3M (2021) to $102.5M (2022), a 17.4% YoY increase. EBITDA margin stable at 22-23%. Growth strategy includes organic expansion and strategic acquisitions.

Key Numbers: 450 locations, $87.3M (2021), $102.5M (2022), 17.4% growth, 22-23% margin"""

    print("EXPECTED OUTPUT:")
    print("=" * 60)
    print(expected)
