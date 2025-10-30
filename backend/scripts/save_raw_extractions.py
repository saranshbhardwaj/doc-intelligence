#!/usr/bin/env python3
"""Extract and save raw text from both parsers for direct comparison"""
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(backend_path / ".env")

from app.services.parsers.pymupdf_parser import PyMuPDFParser
from app.services.parsers.google_documentai_parser import GoogleDocumentAIParser


async def save_raw_extractions(pdf_path: str, output_dir: str = "logs/raw_extractions"):
    """Extract and save raw text from both parsers"""
    pdf_name = Path(pdf_path).stem
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    print(f"Extracting from: {pdf_path}")
    print(f"Saving to: {output_path}\n")

    # Extract with PyMuPDF
    print("1. Extracting with PyMuPDF...")
    pymupdf_parser = PyMuPDFParser()
    pymupdf_result = await pymupdf_parser.parse(pdf_path, "digital")

    pymupdf_file = output_path / f"{timestamp}_{pdf_name}_pymupdf.txt"
    with open(pymupdf_file, 'w', encoding='utf-8') as f:
        f.write(f"PDF: {pdf_path}\n")
        f.write(f"Parser: PyMuPDF {pymupdf_result.parser_version}\n")
        f.write(f"Pages: {pymupdf_result.page_count}\n")
        f.write(f"Characters: {len(pymupdf_result.text):,}\n")
        f.write(f"Processing Time: {pymupdf_result.processing_time_ms}ms\n")
        f.write(f"Cost: ${pymupdf_result.cost_usd:.4f}\n")
        f.write("=" * 80 + "\n\n")
        f.write(pymupdf_result.text)

    print(f"   ✓ Saved: {pymupdf_file}")
    print(f"   - Pages: {pymupdf_result.page_count}")
    print(f"   - Characters: {len(pymupdf_result.text):,}")
    print(f"   - Time: {pymupdf_result.processing_time_ms}ms\n")

    # Extract with Google Document AI
    print("2. Extracting with Google Document AI (batch processing)...")
    try:
        google_parser = GoogleDocumentAIParser()
        google_result = await google_parser.parse(pdf_path, "digital")

        google_file = output_path / f"{timestamp}_{pdf_name}_google_documentai.txt"
        with open(google_file, 'w', encoding='utf-8') as f:
            f.write(f"PDF: {pdf_path}\n")
            f.write(f"Parser: Google Document AI {google_result.parser_version}\n")
            f.write(f"Pages: {google_result.page_count}\n")
            f.write(f"Characters: {len(google_result.text):,}\n")
            f.write(f"Processing Time: {google_result.processing_time_ms}ms\n")
            f.write(f"Cost: ${google_result.cost_usd:.4f}\n")
            f.write(f"Processing Mode: {google_result.metadata.get('processing_mode', 'N/A')}\n")
            if 'json_file_count' in google_result.metadata:
                f.write(f"JSON Files Processed: {google_result.metadata['json_file_count']}\n")
            f.write("=" * 80 + "\n\n")
            f.write(google_result.text)

        print(f"   ✓ Saved: {google_file}")
        print(f"   - Pages: {google_result.page_count}")
        print(f"   - Characters: {len(google_result.text):,}")
        print(f"   - Time: {google_result.processing_time_ms}ms")
        print(f"   - Cost: ${google_result.cost_usd:.4f}\n")

        # Create comparison summary
        summary_file = output_path / f"{timestamp}_{pdf_name}_comparison_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("EXTRACTION COMPARISON SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"PDF: {pdf_path}\n")
            f.write(f"Timestamp: {timestamp}\n\n")

            f.write("PyMuPDF (Free):\n")
            f.write(f"  - File: {pymupdf_file.name}\n")
            f.write(f"  - Pages: {pymupdf_result.page_count}\n")
            f.write(f"  - Characters: {len(pymupdf_result.text):,}\n")
            f.write(f"  - Time: {pymupdf_result.processing_time_ms}ms\n")
            f.write(f"  - Cost: $0.00\n\n")

            f.write("Google Document AI:\n")
            f.write(f"  - File: {google_file.name}\n")
            f.write(f"  - Pages: {google_result.page_count}\n")
            f.write(f"  - Characters: {len(google_result.text):,}\n")
            f.write(f"  - Time: {google_result.processing_time_ms}ms\n")
            f.write(f"  - Cost: ${google_result.cost_usd:.4f}\n\n")

            char_diff = len(google_result.text) - len(pymupdf_result.text)
            char_diff_pct = (char_diff / len(pymupdf_result.text) * 100) if len(pymupdf_result.text) > 0 else 0

            f.write("Difference:\n")
            f.write(f"  - Characters: {char_diff:+,} ({char_diff_pct:+.1f}%)\n")
            f.write(f"  - Speed: Google is {google_result.processing_time_ms / pymupdf_result.processing_time_ms:.0f}x slower\n")

            # Token estimation (rough: 1 token ≈ 4 chars)
            pymupdf_tokens = len(pymupdf_result.text) / 4
            google_tokens = len(google_result.text) / 4
            token_diff = google_tokens - pymupdf_tokens

            f.write(f"\nEstimated Token Usage (for LLM):\n")
            f.write(f"  - PyMuPDF: ~{pymupdf_tokens:,.0f} tokens\n")
            f.write(f"  - Google Document AI: ~{google_tokens:,.0f} tokens\n")
            f.write(f"  - Token savings: ~{abs(token_diff):,.0f} tokens ({abs(char_diff_pct):.1f}%)\n")

            # Cost calculation at Claude's rate ($3/MTok input)
            pymupdf_llm_cost = (pymupdf_tokens / 1_000_000) * 3
            google_llm_cost = (google_tokens / 1_000_000) * 3

            f.write(f"\nEstimated LLM Cost (Claude Sonnet @ $3/MTok input):\n")
            f.write(f"  - PyMuPDF → LLM: ${pymupdf_llm_cost:.4f}\n")
            f.write(f"  - Google → LLM: ${google_llm_cost:.4f}\n")
            f.write(f"  - LLM savings: ${abs(google_llm_cost - pymupdf_llm_cost):.4f}\n")

            f.write(f"\nTotal Cost (Parsing + LLM):\n")
            f.write(f"  - PyMuPDF: ${pymupdf_llm_cost:.4f} (parsing free)\n")
            f.write(f"  - Google: ${google_result.cost_usd + google_llm_cost:.4f} (${google_result.cost_usd:.4f} parsing + ${google_llm_cost:.4f} LLM)\n")

        print(f"   ✓ Saved summary: {summary_file}\n")

        print("=" * 80)
        print("FILES SAVED:")
        print("=" * 80)
        print(f"1. PyMuPDF extraction:     {pymupdf_file}")
        print(f"2. Google AI extraction:   {google_file}")
        print(f"3. Comparison summary:     {summary_file}")
        print("=" * 80)

    except Exception as e:
        print(f"   ✗ Google Document AI failed: {e}\n")
        print(f"Saved PyMuPDF extraction only: {pymupdf_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python save_raw_extractions.py <path_to_pdf>")
        print("\nExample:")
        print("  python scripts/save_raw_extractions.py tests/data/sample_cims/CIM-06-Pizza-Hut.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    asyncio.run(save_raw_extractions(pdf_path))
