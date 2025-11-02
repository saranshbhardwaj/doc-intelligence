"""Example script showing how to identify and process chunks with tables.

This demonstrates different ways to work with the chunked data:
1. Identify which chunks have tables
2. Separate narrative text from tables
3. Process tables differently than narrative text

Run after generating chunks with chunk_azure_response.py
"""
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/example_chunk_processing.py logs/chunks/..._chunks.json")
        sys.exit(1)

    chunks_path = Path(sys.argv[1])
    if not chunks_path.exists():
        print(f"Error: File not found: {chunks_path}")
        sys.exit(1)

    # Load chunks
    with open(chunks_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = data["chunks"]
    print(f"Loaded {len(chunks)} chunks from {chunks_path.name}\n")

    # ========================================
    # Method 1: Identify chunks with tables via metadata
    # ========================================
    print("="*60)
    print("METHOD 1: Identify chunks with tables (via metadata)")
    print("="*60)

    chunks_with_tables = [c for c in chunks if c["metadata"]["has_tables"]]
    print(f"\nFound {len(chunks_with_tables)} chunks with tables:\n")

    for chunk in chunks_with_tables:
        page_num = chunk["metadata"]["page_number"]
        table_count = chunk["metadata"]["table_count"]
        print(f"  - Page {page_num}: {table_count} table(s)")

    # ========================================
    # Method 2: Access separated table data
    # ========================================
    print("\n" + "="*60)
    print("METHOD 2: Access separated table data")
    print("="*60)

    if chunks_with_tables:
        example_chunk = chunks_with_tables[0]
        print(f"\nExample: Page {example_chunk['metadata']['page_number']}")
        print(f"Narrative char count: {example_chunk['metadata']['narrative_char_count']}")
        print(f"Total char count (with tables): {example_chunk['metadata']['char_count']}")
        print(f"Number of tables: {len(example_chunk['tables'])}\n")

        # Show each table separately
        for table in example_chunk["tables"]:
            print(f"Table {table['table_id']}: {table['row_count']}x{table['column_count']}")
            print(f"Table text (first 200 chars):\n{table['text'][:200]}...\n")

    # ========================================
    # Method 3: Process narrative vs tables separately
    # ========================================
    print("="*60)
    print("METHOD 3: Process narrative vs tables separately")
    print("="*60)

    if chunks_with_tables:
        example_chunk = chunks_with_tables[0]

        print(f"\nNarrative text only (first 150 chars):")
        print(f"{example_chunk['narrative_text'][:150]}...\n")

        print(f"Full text with tables (first 150 chars):")
        print(f"{example_chunk['text'][:150]}...\n")

    # ========================================
    # Method 4: Different LLM prompts for narrative vs tables
    # ========================================
    print("="*60)
    print("METHOD 4: Example LLM processing strategy")
    print("="*60)

    print("\nYou could process chunks differently based on content:\n")

    for i, chunk in enumerate(chunks[:3], 1):  # Just show first 3 as examples
        page_num = chunk["metadata"]["page_number"]
        has_tables = chunk["metadata"]["has_tables"]

        if has_tables:
            print(f"Chunk {i} (Page {page_num}) - HAS TABLES:")
            print(f"  → Send narrative to cheap LLM for summary")
            print(f"  → Send tables to specialized table extraction LLM")
            print(f"  → Combine both for final expensive LLM call\n")
        else:
            print(f"Chunk {i} (Page {page_num}) - NO TABLES:")
            print(f"  → Send full text to cheap LLM for summary")
            print(f"  → Use summary in final expensive LLM call\n")

    # ========================================
    # Method 5: Check for tables using text markers
    # ========================================
    print("="*60)
    print("METHOD 5: Identify tables using text markers")
    print("="*60)

    print("\nAlternate way to detect tables (if metadata not available):\n")

    for chunk in chunks[:3]:
        page_num = chunk["metadata"]["page_number"]
        has_table_marker = "[Table]" in chunk["text"]
        has_tables_metadata = chunk["metadata"]["has_tables"]

        print(f"Page {page_num}:")
        print(f"  - Metadata says has_tables: {has_tables_metadata}")
        print(f"  - Text contains '[Table]' marker: {has_table_marker}")
        print(f"  - Match: {'✓' if has_table_marker == has_tables_metadata else '✗'}\n")


if __name__ == "__main__":
    main()
