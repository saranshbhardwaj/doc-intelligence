"""Chunk a saved Azure Document Intelligence response into page-wise chunks.

UPDATED: Now uses the production chunking infrastructure from app/services/chunkers.
This script is now a thin wrapper for testing the production code.

Usage:
    python scripts/chunk_azure_response.py logs/azure_raw/2025-11-01_10-53-51_CIM-06-Pizza-Hut_298256c6.json

Outputs:
    - logs/chunks/<timestamp>_<filename>_chunks.json (all chunks in one file)
    - Console summary of chunk statistics
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

from app.config import settings
from app.utils.logging import logger
from app.services.chunkers import ChunkerFactory
from app.services.parsers.base import ParserOutput


def extract_page_wise_chunks_legacy(azure_response: dict) -> list[dict]:
    """Legacy method - kept for backward compatibility with old test data."""
    """Extract page-wise chunks from Azure response.

    Strategy:
    - Each page = 1 chunk
    - Tables are separated from narrative text for flexible processing
    - Preserve metadata: page number, char count, table count

    Args:
        azure_response: The saved Azure JSON from azure_parse_test.py

    Returns:
        List of chunk dictionaries with structure:
        {
            "chunk_id": "page_1",
            "text": "Full page text with tables embedded (for LLM context)",
            "narrative_text": "Just the narrative text (no tables)",
            "tables": [
                {
                    "table_id": 0,
                    "text": "Tab-separated table text",
                    "row_count": 8,
                    "column_count": 3,
                    "cells": [...original cell data...]
                }
            ],
            "metadata": {
                "page_number": 1,
                "char_count": 423,
                "narrative_char_count": 380,
                "table_count": 0,
                "chunk_type": "page",
                "has_tables": False,
                "source_page_width": 8.2639,
                "source_page_height": 11.6944,
                "source_page_unit": "inch"
            }
        }
    """
    analyze_result = azure_response.get("analyzeResult", {})
    pages = analyze_result.get("pages", [])
    tables = analyze_result.get("tables", [])

    # Build a map of tables by page number for easy lookup
    tables_by_page = {}
    for table in tables:
        page_num = table.get("pageNumber")
        if page_num:
            tables_by_page.setdefault(page_num, []).append(table)

    chunks = []

    for page in pages:
        page_num = page.get("pageNumber")

        # Extract narrative text from lines
        lines = page.get("lines", [])
        line_texts = [line.get("content", "") for line in lines]
        narrative_text = "\n".join(line_texts)

        # Process tables for this page separately
        page_tables_data = []
        page_tables = tables_by_page.get(page_num, [])

        for table_idx, table in enumerate(page_tables):
            # Reconstruct table as tab-separated text
            row_count = table.get("rowCount", 0)
            col_count = table.get("columnCount", 0)
            cells = table.get("cells", [])

            # Build matrix
            matrix = [["" for _ in range(col_count)] for _ in range(row_count)]
            for cell in cells:
                row_idx = cell.get("rowIndex", 0)
                col_idx = cell.get("columnIndex", 0)
                content = cell.get("content", "")
                if row_idx < row_count and col_idx < col_count:
                    matrix[row_idx][col_idx] = content

            # Render as text
            table_text_lines = ["\t".join(row) for row in matrix]
            table_text = "\n".join(table_text_lines)

            # Store table data separately
            page_tables_data.append({
                "table_id": table_idx,
                "text": table_text,
                "row_count": row_count,
                "column_count": col_count,
                "cells": cells,  # Keep original cell data for advanced processing
            })

        # Build full text with embedded tables (for LLM context)
        full_text = narrative_text
        for table_data in page_tables_data:
            full_text += f"\n\n[Table]\n{table_data['text']}\n"

        # Build chunk
        chunk = {
            "chunk_id": f"page_{page_num}",
            "text": full_text.strip(),  # Full text with tables (for LLM)
            "narrative_text": narrative_text.strip(),  # Just narrative (no tables)
            "tables": page_tables_data,  # Separate table data
            "metadata": {
                "page_number": page_num,
                "char_count": len(full_text.strip()),
                "narrative_char_count": len(narrative_text.strip()),
                "table_count": len(page_tables_data),
                "chunk_type": "page",
                "has_tables": len(page_tables_data) > 0,
                "source_page_width": page.get("width"),
                "source_page_height": page.get("height"),
                "source_page_unit": page.get("unit"),
            }
        }

        chunks.append(chunk)

    return chunks


def save_chunks(chunks: list[dict], output_path: Path) -> None:
    """Save chunks to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Prepare output structure
    output = {
        "chunk_strategy": "page_wise",
        "chunk_count": len(chunks),
        "total_chars": sum(c["metadata"]["char_count"] for c in chunks),
        "avg_chars_per_chunk": sum(c["metadata"]["char_count"] for c in chunks) / len(chunks) if chunks else 0,
        "pages_with_tables": sum(1 for c in chunks if c["metadata"]["has_tables"]),
        "total_tables": sum(c["metadata"]["table_count"] for c in chunks),
        "created_at": datetime.now().isoformat(),
        "chunks": chunks
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(chunks)} chunks to {output_path}")


def print_summary(chunks: list[dict]) -> None:
    """Print summary statistics about the chunks."""
    print("\n" + "="*50)
    print("PAGE-WISE CHUNKING SUMMARY")
    print("="*50)
    print(f"Total chunks (pages): {len(chunks)}")
    print(f"Total characters: {sum(c['metadata']['char_count'] for c in chunks):,}")
    print(f"Avg chars/chunk: {sum(c['metadata']['char_count'] for c in chunks) / len(chunks):.0f}")
    print(f"Pages with tables: {sum(1 for c in chunks if c['metadata']['has_tables'])}")
    print(f"Total tables: {sum(c['metadata']['table_count'] for c in chunks)}")

    # Find largest and smallest chunks
    if chunks:
        largest = max(chunks, key=lambda c: c["metadata"]["char_count"])
        smallest = min(chunks, key=lambda c: c["metadata"]["char_count"])
        print(f"\nLargest chunk: Page {largest['metadata']['page_number']} ({largest['metadata']['char_count']} chars, {largest['metadata']['table_count']} tables)")
        print(f"Smallest chunk: Page {smallest['metadata']['page_number']} ({smallest['metadata']['char_count']} chars, {smallest['metadata']['table_count']} tables)")

    # Show first chunk preview
    if chunks:
        print(f"\n--- Preview of first chunk (Page 1) ---")
        preview_text = chunks[0]["text"][:300].replace("\n", " ")
        print(f"{preview_text}...")

    print("="*50 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Chunk a saved Azure response into page-wise chunks"
    )
    parser.add_argument(
        "azure_json_path",
        type=str,
        help="Path to saved Azure JSON (from logs/azure_raw/)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Custom output path (default: logs/chunks/<timestamp>_chunks.json)"
    )

    args = parser.parse_args()

    # Load Azure response
    azure_path = Path(args.azure_json_path)
    if not azure_path.exists():
        print(f"Error: File not found: {azure_path}")
        sys.exit(1)

    print(f"Loading Azure response from: {azure_path.name}")
    with open(azure_path, "r", encoding="utf-8") as f:
        azure_response = json.load(f)

    # Extract chunks using production infrastructure
    print("Extracting page-wise chunks using production chunker...")

    # Reconstruct ParserOutput from saved Azure JSON
    analyze_result = azure_response.get("analyzeResult", {})
    summary = azure_response.get("summary", {})

    # Build ParserOutput object
    parser_output = ParserOutput(
        text=analyze_result.get("content", ""),
        page_count=summary.get("page_count", 0),
        parser_name="azure_document_intelligence",
        parser_version="1.0.0",
        processing_time_ms=0,
        cost_usd=summary.get("cost_usd", 0.0),
        pdf_type="digital",
        metadata={
            "pages_data": [
                {
                    "page_number": page.get("pageNumber"),
                    "text": page.get("text", ""),
                    "narrative_text": page.get("text", ""),  # Simplified for test script
                    "tables": [],  # Tables already embedded in text
                    "table_count": page.get("tableCount", 0),
                    "char_count": page.get("charCount", 0),
                }
                for page in analyze_result.get("pages", [])
            ]
        }
    )

    # Use production chunker
    chunker = ChunkerFactory.get_chunker("azure_document_intelligence")
    if not chunker:
        print("ERROR: Azure chunker not available. Using legacy method.")
        chunks = extract_page_wise_chunks_legacy(azure_response)
    else:
        chunking_output = chunker.chunk(parser_output)
        # Convert Chunk objects to dict format for saving
        chunks = [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "narrative_text": chunk.narrative_text,
                "tables": chunk.tables,
                "metadata": chunk.metadata
            }
            for chunk in chunking_output.chunks
        ]
        print(f"✓ Used production chunker: {chunker.name}")

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        chunks_dir = settings.log_dir / "chunks"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Extract original filename from azure_path
        # Format: 2025-11-01_10-53-51_CIM-06-Pizza-Hut_298256c6.json
        original_name = azure_path.stem.split("_", 3)[-1] if "_" in azure_path.stem else azure_path.stem
        output_path = chunks_dir / f"{timestamp}_{original_name}_chunks.json"

    # Save chunks
    save_chunks(chunks, output_path)

    # Print summary
    print_summary(chunks)

    print(f"✓ Chunks saved to: {output_path}")
    print(f"✓ Ready for Step 3: LLM processing\n")


if __name__ == "__main__":
    main()
