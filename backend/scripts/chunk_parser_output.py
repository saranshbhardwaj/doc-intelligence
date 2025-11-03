#!/usr/bin/env python3
"""Chunk a saved ParserOutput from production parser.

This script loads ParserOutput saved by save_azure_parser_output.py and runs
it through the production chunker.

Usage:
    python scripts/chunk_parser_output.py logs/parser_outputs/2025-11-02_XX-XX-XX_CIM-06-Pizza-Hut_parser_output.json

Outputs:
    - logs/chunks/<timestamp>_<filename>_chunks.json
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


def load_parser_output(json_path: Path) -> ParserOutput:
    """Load ParserOutput from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Reconstruct ParserOutput object
    return ParserOutput(
        text=data["text"],
        page_count=data["page_count"],
        parser_name=data["parser_name"],
        parser_version=data["parser_version"],
        processing_time_ms=data["processing_time_ms"],
        cost_usd=data["cost_usd"],
        pdf_type=data["pdf_type"],
        metadata=data["metadata"]
    )


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
        description="Chunk a saved ParserOutput from production parser"
    )
    parser.add_argument(
        "parser_output_path",
        type=str,
        help="Path to saved ParserOutput JSON (from logs/parser_outputs/)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Custom output path (default: logs/chunks/<timestamp>_chunks.json)"
    )

    args = parser.parse_args()

    # Load ParserOutput
    parser_output_path = Path(args.parser_output_path)
    if not parser_output_path.exists():
        print(f"Error: File not found: {parser_output_path}")
        sys.exit(1)

    print(f"Loading ParserOutput from: {parser_output_path.name}")
    parser_output = load_parser_output(parser_output_path)

    print(f"  - Parser: {parser_output.parser_name}")
    print(f"  - Pages: {parser_output.page_count}")
    print(f"  - Total chars: {len(parser_output.text):,}")
    print(f"  - Tables: {parser_output.metadata.get('total_tables', 0)}")

    # Use production chunker
    print("\nChunking using production chunker...")
    chunker = ChunkerFactory.get_chunker(parser_output.parser_name)
    if not chunker:
        print(f"ERROR: No chunker available for parser '{parser_output.parser_name}'")
        sys.exit(1)

    chunking_output = chunker.chunk(parser_output)
    print(f"✓ Used production chunker: {chunker.name}")

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

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        chunks_dir = settings.log_dir / "chunks"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Extract original filename from parser_output_path
        original_name = parser_output_path.stem.replace("_parser_output", "")
        output_path = chunks_dir / f"{timestamp}_{original_name}_chunks.json"

    # Save chunks
    save_chunks(chunks, output_path)

    # Print summary
    print_summary(chunks)

    print(f"✓ Chunks saved to: {output_path}")
    print(f"✓ Ready for LLM processing\n")


if __name__ == "__main__":
    main()
