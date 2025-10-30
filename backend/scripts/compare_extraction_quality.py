#!/usr/bin/env python3
"""Compare extraction quality between PyMuPDF and Google Document AI"""
import sys
import asyncio
from pathlib import Path
from difflib import SequenceMatcher

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(backend_path / ".env")

from app.services.parsers.pymupdf_parser import PyMuPDFParser
from app.services.parsers.google_documentai_parser import GoogleDocumentAIParser


def show_text_comparison(text1: str, text2: str, label1: str, label2: str, sample_length: int = 1000):
    """Show side-by-side comparison of text samples"""
    print(f"\n{'=' * 80}")
    print(f"TEXT SAMPLE COMPARISON (first {sample_length} characters)")
    print(f"{'=' * 80}\n")

    print(f"{label1}:")
    print("-" * 80)
    print(text1[:sample_length])
    print()

    print(f"{label2}:")
    print("-" * 80)
    print(text2[:sample_length])
    print()


def analyze_differences(text1: str, text2: str, label1: str, label2: str):
    """Analyze differences between two text extractions"""
    print(f"\n{'=' * 80}")
    print(f"DIFFERENCE ANALYSIS")
    print(f"{'=' * 80}\n")

    # Basic stats
    print(f"{label1}:")
    print(f"  - Total characters: {len(text1):,}")
    print(f"  - Total words: {len(text1.split()):,}")
    print(f"  - Total lines: {len(text1.splitlines()):,}")
    print(f"  - Whitespace ratio: {text1.count(' ') / len(text1) * 100:.1f}%")
    print()

    print(f"{label2}:")
    print(f"  - Total characters: {len(text2):,}")
    print(f"  - Total words: {len(text2.split()):,}")
    print(f"  - Total lines: {len(text2.splitlines()):,}")
    print(f"  - Whitespace ratio: {text2.count(' ') / len(text2) * 100:.1f}%")
    print()

    # Similarity ratio
    similarity = SequenceMatcher(None, text1, text2).ratio()
    print(f"Text Similarity: {similarity * 100:.1f}%")

    # Character difference
    char_diff = len(text2) - len(text1)
    char_diff_pct = (char_diff / len(text1) * 100) if len(text1) > 0 else 0
    print(f"Character Difference: {char_diff:+,} ({char_diff_pct:+.1f}%)")

    # Find unique words
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    unique_to_1 = words1 - words2
    unique_to_2 = words2 - words1

    print(f"\nUnique words in {label1}: {len(unique_to_1)}")
    if len(unique_to_1) > 0 and len(unique_to_1) <= 20:
        print(f"  Examples: {', '.join(list(unique_to_1)[:10])}")

    print(f"Unique words in {label2}: {len(unique_to_2)}")
    if len(unique_to_2) > 0 and len(unique_to_2) <= 20:
        print(f"  Examples: {', '.join(list(unique_to_2)[:10])}")


async def compare_extraction_quality(pdf_path: str):
    """Compare extraction quality between PyMuPDF and Google Document AI"""
    print("=" * 80)
    print("EXTRACTION QUALITY COMPARISON")
    print("=" * 80)
    print(f"\nTest PDF: {pdf_path}\n")

    # Extract with PyMuPDF
    print("Extracting with PyMuPDF...")
    pymupdf_parser = PyMuPDFParser()
    pymupdf_result = await pymupdf_parser.parse(pdf_path, "digital")
    print(f"✓ PyMuPDF: {pymupdf_result.page_count} pages, {len(pymupdf_result.text):,} chars")

    # Extract with Google Document AI
    print("\nExtracting with Google Document AI (this may take 1-2 minutes)...")
    try:
        google_parser = GoogleDocumentAIParser()
        google_result = await google_parser.parse(pdf_path, "digital")
        print(f"✓ Google Document AI: {google_result.page_count} pages, {len(google_result.text):,} chars")

        # Show detailed comparison
        show_text_comparison(
            pymupdf_result.text,
            google_result.text,
            "PyMuPDF (Free)",
            "Google Document AI"
        )

        # Analyze differences
        analyze_differences(
            pymupdf_result.text,
            google_result.text,
            "PyMuPDF",
            "Google Document AI"
        )

        # Show metadata
        print(f"\n{'=' * 80}")
        print("METADATA COMPARISON")
        print(f"{'=' * 80}\n")

        print("PyMuPDF metadata:")
        for key, value in pymupdf_result.metadata.items():
            print(f"  {key}: {value}")

        print("\nGoogle Document AI metadata:")
        for key, value in google_result.metadata.items():
            print(f"  {key}: {value}")

        # Quality verdict
        print(f"\n{'=' * 80}")
        print("QUALITY VERDICT")
        print(f"{'=' * 80}\n")

        if len(pymupdf_result.text) > len(google_result.text) * 1.02:
            print("✓ PyMuPDF extracted MORE text (+2% threshold)")
            print(f"  Difference: +{len(pymupdf_result.text) - len(google_result.text):,} chars")
        elif len(google_result.text) > len(pymupdf_result.text) * 1.02:
            print("✓ Google Document AI extracted MORE text (+2% threshold)")
            print(f"  Difference: +{len(google_result.text) - len(pymupdf_result.text):,} chars")
        else:
            print("✓ Both parsers extracted SIMILAR amounts of text")
            print(f"  Difference: {abs(len(pymupdf_result.text) - len(google_result.text)):,} chars (< 2%)")

        print(f"\nRecommendation for digital PDFs:")
        if pymupdf_result.processing_time_ms < google_result.processing_time_ms / 10:
            speed_factor = google_result.processing_time_ms / pymupdf_result.processing_time_ms
            print(f"  Use PyMuPDF - {speed_factor:.0f}x faster, free, similar quality")
        else:
            print(f"  Both are acceptable, but PyMuPDF is free")

    except Exception as e:
        print(f"\n✗ Google Document AI failed: {e}")
        print("\nShowing PyMuPDF-only results:")
        print(f"\n{pymupdf_result.text[:2000]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compare_extraction_quality.py <path_to_pdf>")
        print("\nExample:")
        print("  python scripts/compare_extraction_quality.py tests/data/sample_cims/CIM-06-Pizza-Hut.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    asyncio.run(compare_extraction_quality(pdf_path))
