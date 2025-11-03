#!/usr/bin/env python3
"""Parse PDF with production AzureDocumentIntelligenceParser and save complete ParserOutput.

This script uses the PRODUCTION parser (not the test script) to ensure the output
has the exact same structure as what the chunker expects.

Usage:
    python scripts/save_azure_parser_output.py tests/data/sample_cims/CIM-06-Pizza-Hut.pdf

Outputs:
    - logs/parser_outputs/<timestamp>_<filename>_parser_output.json

This output can then be used with chunk_azure_response.py for testing chunking
without calling Azure API again.
"""
import sys
import asyncio
import json
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(backend_path / ".env")

from app.services.parsers.azure_document_intelligence_parser import AzureDocumentIntelligenceParser
from app.utils.logging import logger


async def save_parser_output(pdf_path: str, output_dir: str = "logs/parser_outputs"):
    """Parse PDF with production parser and save complete ParserOutput"""
    pdf_name = Path(pdf_path).stem
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    print(f"Parsing PDF: {pdf_path}")
    print(f"Using: AzureDocumentIntelligenceParser (production)\n")

    # Parse with production Azure parser
    parser = AzureDocumentIntelligenceParser()

    try:
        parser_output = await parser.parse(pdf_path, "digital")
    except Exception as e:
        print(f"❌ Parsing failed: {e}")
        sys.exit(1)

    # Convert ParserOutput to JSON-serializable dict
    output_data = {
        "text": parser_output.text,
        "page_count": parser_output.page_count,
        "parser_name": parser_output.parser_name,
        "parser_version": parser_output.parser_version,
        "processing_time_ms": parser_output.processing_time_ms,
        "cost_usd": parser_output.cost_usd,
        "pdf_type": parser_output.pdf_type,
        "metadata": parser_output.metadata,
        "saved_at": timestamp,
        "source_pdf": str(pdf_path),
    }

    # Save to JSON
    output_file = output_path / f"{timestamp}_{pdf_name}_parser_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"✓ Parsing completed successfully")
    print(f"  - Pages: {parser_output.page_count}")
    print(f"  - Characters: {len(parser_output.text):,}")
    print(f"  - Tables: {parser_output.metadata.get('total_tables', 0)}")
    print(f"  - Processing time: {parser_output.processing_time_ms}ms")
    print(f"  - Cost: ${parser_output.cost_usd:.4f}")
    print(f"\n✓ Saved to: {output_file}")
    print(f"\nNext step:")
    print(f"  python scripts/chunk_parser_output.py {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/save_azure_parser_output.py <pdf_path>")
        print("Example: python scripts/save_azure_parser_output.py tests/data/sample_cims/CIM-06-Pizza-Hut.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    asyncio.run(save_parser_output(pdf_path))
