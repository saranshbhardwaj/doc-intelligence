#!/usr/bin/env python3
"""Compare parser outputs without LLM call - just parsing quality"""
import sys
import time
import asyncio
import json
import difflib
from pathlib import Path
from dotenv import load_dotenv
import os

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

# Load environment variables from .env file
load_dotenv(backend_path / ".env")

# Normalize GOOGLE_APPLICATION_CREDENTIALS path if relative
gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if gac and not os.path.isabs(gac):
    abs_gac = str((backend_path / gac).resolve())
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_gac

from app.services.parsers.pymupdf_parser import PyMuPDFParser
from app.services.parsers.google_documentai_parser import GoogleDocumentAIParser
from app.config import settings


def _save_output(base_stem: str, parser_key: str, text: str, meta: dict):
    """Persist parser output and metadata to logs/parsed"""
    out_dir = settings.parsed_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    text_file = out_dir / f"{parser_key}_{base_stem}.txt"
    meta_file = out_dir / f"{parser_key}_{base_stem}.meta.json"
    text_file.write_text(text)
    meta_file.write_text(json.dumps(meta, indent=2))
    return text_file, meta_file


def _build_diff_sample(a_text: str, b_text: str, max_lines: int = 120):
    a_lines = a_text.splitlines()
    b_lines = b_text.splitlines()
    diff = list(difflib.unified_diff(a_lines, b_lines, fromfile="pymupdf", tofile="google_documentai", lineterm="", n=2))
    if len(diff) > max_lines:
        diff = diff[:max_lines] + ["... (truncated)"]
    return diff


async def compare_parsers(pdf_path: str):
    """Compare PyMuPDF vs Google Document AI parsing quality
    
    Args:
        pdf_path: Path to PDF file to test
    """
    print("=" * 80)
    print("PARSER COMPARISON TEST (No LLM - Just Parsing)")
    print("=" * 80)
    print(f"\nTest PDF: {pdf_path}\n")

    # Get file size
    file_size = Path(pdf_path).stat().st_size
    print(f"PDF Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)\n")

    results = {}
    base_stem = Path(pdf_path).stem

    # Test 1: PyMuPDF
    print("-" * 80)
    print("TEST 1: PyMuPDF (Free)")
    print("-" * 80)
    try:
        parser1 = PyMuPDFParser()
        start = time.time()
        output1 = await parser1.parse(pdf_path, "digital")
        elapsed1 = time.time() - start
        
        results['pymupdf'] = {
            'parser': 'PyMuPDF',
            'pages': output1.page_count,
            'chars': len(output1.text),
            'time_sec': elapsed1,
            'cost_usd': output1.cost_usd,
            'text_sample': output1.text[:500],
            'success': True,
        }
        _save_output(base_stem, 'pymupdf', output1.text, {
            'pages': output1.page_count,
            'chars': len(output1.text),
            'processing_time_ms': output1.processing_time_ms,
            'cost_usd': output1.cost_usd,
            'parser_version': output1.parser_version,
            'avg_chars_per_page': len(output1.text) / output1.page_count if output1.page_count else 0,
        })
        
        print(f"✓ Pages detected: {output1.page_count}")
        print(f"✓ Characters extracted: {len(output1.text):,}")
        print(f"✓ Processing time: {elapsed1:.2f}s")
        print(f"✓ Cost: ${output1.cost_usd:.4f}")
        print(f"✓ Avg chars/page: {len(output1.text) / output1.page_count if output1.page_count > 0 else 0:.0f}")
        print(f"\nText sample (first 200 chars):")
        print(output1.text[:200].replace('\n', ' '))
        
    except Exception as e:
        results['pymupdf'] = {'success': False, 'error': str(e)}
        print(f"✗ FAILED: {e}")
    
    print()
    
    # Test 2: Google Document AI
    print("-" * 80)
    print("TEST 2: Google Document AI")
    print("-" * 80)
    try:
        parser2 = GoogleDocumentAIParser()
        start = time.time()
        output2 = await parser2.parse(pdf_path, "digital")
        elapsed2 = time.time() - start
        
        results['documentai'] = {
            'parser': 'Google Document AI',
            'pages': output2.page_count,
            'chars': len(output2.text),
            'time_sec': elapsed2,
            'cost_usd': output2.cost_usd,
            'text_sample': output2.text[:500],
            'success': True,
        }
        _save_output(base_stem, 'google_documentai', output2.text, {
            'pages': output2.page_count,
            'chars': len(output2.text),
            'processing_time_ms': output2.processing_time_ms,
            'cost_usd': output2.cost_usd,
            'parser_version': output2.parser_version,
            'avg_chars_per_page': len(output2.text) / output2.page_count if output2.page_count else 0,
        })
        
        print(f"✓ Pages detected: {output2.page_count}")
        print(f"✓ Characters extracted: {len(output2.text):,}")
        print(f"✓ Processing time: {elapsed2:.2f}s")
        print(f"✓ Cost: ${output2.cost_usd:.4f}")
        print(f"✓ Avg chars/page: {len(output2.text) / output2.page_count if output2.page_count > 0 else 0:.0f}")
        print(f"\nText sample (first 200 chars):")
        print(output2.text[:200].replace('\n', ' '))
        
    except Exception as e:
        results['documentai'] = {'success': False, 'error': str(e)}
        print(f"✗ FAILED: {e}")
    
    print()
    
    # Comparison Summary
    print("=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    
    if results['pymupdf']['success'] and results['documentai']['success']:
        print(f"\n{'Metric':<25} {'PyMuPDF':<20} {'Document AI':<20} {'Winner':<15}")
        print("-" * 80)
        
        # Pages
        p1_pages = results['pymupdf']['pages']
        p2_pages = results['documentai']['pages']
        winner_pages = "PyMuPDF" if p1_pages >= p2_pages else "Document AI"
        print(f"{'Pages Detected':<25} {p1_pages:<20} {p2_pages:<20} {winner_pages:<15}")
        
        # Characters
        p1_chars = results['pymupdf']['chars']
        p2_chars = results['documentai']['chars']
        char_diff = ((p2_chars - p1_chars) / p1_chars * 100) if p1_chars > 0 else 0
        winner_chars = "PyMuPDF" if p1_chars >= p2_chars else "Document AI"
        print(f"{'Characters Extracted':<25} {f'{p1_chars:,}':<20} {f'{p2_chars:,}':<20} {winner_chars:<15}")
        print(f"{'  (Difference)':<25} {'-':<20} {f'{char_diff:+.1f}%':<20}")
        
        # Time
        p1_time = results['pymupdf']['time_sec']
        p2_time = results['documentai']['time_sec']
        winner_time = "PyMuPDF" if p1_time <= p2_time else "Document AI"
        print(f"{'Processing Time':<25} {f'{p1_time:.2f}s':<20} {f'{p2_time:.2f}s':<20} {winner_time:<15}")
        
        # Cost
        p1_cost = results['pymupdf']['cost_usd']
        p2_cost = results['documentai']['cost_usd']
        winner_cost = "PyMuPDF" if p1_cost <= p2_cost else "Document AI"
        print(f"{'Cost':<25} {f'${p1_cost:.4f}':<20} {f'${p2_cost:.4f}':<20} {winner_cost:<15}")
        
        print()
        print("RECOMMENDATION:")
        if p1_pages == p2_pages and p1_chars >= p2_chars * 0.95 and p1_cost == 0:
            print("✓ Use PyMuPDF - Same quality, free, and faster!")
        elif p2_pages > p1_pages or p2_chars > p1_chars * 1.1:
            print("✓ Use Document AI - Better extraction quality")
        else:
            print("⚠ Both are comparable - PyMuPDF is cheaper")

        # Persist comparison summary & diff
        comparison = {
            'file': str(pdf_path),
            'pymupdf': {
                'pages': p1_pages,
                'chars': p1_chars,
                'time_sec': p1_time,
                'cost_usd': p1_cost,
            },
            'google_documentai': {
                'pages': p2_pages,
                'chars': p2_chars,
                'time_sec': p2_time,
                'cost_usd': p2_cost,
            },
            'char_ratio_google_over_pymupdf': round(p2_chars / p1_chars, 3) if p1_chars else None,
            'diff_sample': _build_diff_sample(results['pymupdf']['text_sample'], results['documentai']['text_sample']),
            'timestamp': time.time(),
        }
        comparison_path = settings.parsed_dir / f"comparison_{base_stem}.json"
        comparison_path.write_text(json.dumps(comparison, indent=2))
        print(f"\nSaved comparison JSON: {comparison_path}")
    
    print()
    print("=" * 80)
    print("NEXT STEP: Inspect saved files in logs/parsed for full text & diff")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compare_parsers.py <path_to_pdf>")
        print("\nExample:")
        print("  python scripts/compare_parsers.py tests/data/sample_cims/CIM-06-Pizza-Hut.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    asyncio.run(compare_parsers(pdf_path))
