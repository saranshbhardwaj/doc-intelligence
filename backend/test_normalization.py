#!/usr/bin/env python3
"""
Test extraction on all CIM documents with new normalization logic.
This is NOT a stress test - just quality testing to verify no validation errors.
"""

import requests
import time
from pathlib import Path
import json

API_URL = "http://localhost:8000"
SAMPLE_CIMS_DIR = Path("tests/data/sample_cims")
OUTPUT_DIR = Path("tests/data/golden_outputs")

def test_document(pdf_path: Path) -> dict:
    """Test extraction on a single document"""
    print(f"\n{'='*70}")
    print(f"📄 Testing: {pdf_path.name}")
    print(f"{'='*70}")

    start_time = time.time()

    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path.name, f, 'application/pdf')}

            print("⏳ Uploading document...")
            response = requests.post(
                f"{API_URL}/api/extract",
                files=files,
                timeout=600  # 10 minutes (some docs take 8+ min due to API variance)
            )

            elapsed = time.time() - start_time

            if response.status_code == 200:
                result = response.json()
                if result is None:
                    print(f"❌ FAILED in {elapsed:.1f}s - Empty response")
                    return {
                        'file': pdf_path.name,
                        'success': False,
                        'time': elapsed,
                        'error': 'Empty JSON response'
                    }

                from_cache = result.get('from_cache', False)
                confidence = result.get('data', {}).get('field_confidence', {}).get('overall', 'N/A')

                print(f"✅ SUCCESS in {elapsed:.1f}s {'(cached)' if from_cache else ''}")
                print(f"   Confidence: {confidence}")
                print(f"   Pages: {result.get('metadata', {}).get('pages', 'N/A')}")

                # Save output
                output_file = OUTPUT_DIR / f"{pdf_path.stem}.json"
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                with open(output_file, 'w') as out:
                    json.dump(result, out, indent=2)
                print(f"   Saved to: {output_file}")

                return {
                    'file': pdf_path.name,
                    'success': True,
                    'time': elapsed,
                    'cached': from_cache,
                    'confidence': confidence,
                    'output': output_file
                }
            else:
                error_text = response.text[:200]
                print(f"❌ FAILED (HTTP {response.status_code}) in {elapsed:.1f}s")
                print(f"   Error: {error_text}")

                return {
                    'file': pdf_path.name,
                    'success': False,
                    'time': elapsed,
                    'error': error_text,
                    'status_code': response.status_code
                }

    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"⏱️  TIMEOUT after {elapsed:.1f}s")
        return {
            'file': pdf_path.name,
            'success': False,
            'time': elapsed,
            'error': 'Request timeout'
        }
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"💥 ERROR after {elapsed:.1f}s: {str(e)}")
        return {
            'file': pdf_path.name,
            'success': False,
            'time': elapsed,
            'error': str(e)
        }


def main():
    print("\n" + "="*70)
    print("🧪 Testing New Normalization Logic")
    print("="*70)
    print(f"API: {API_URL}")
    print(f"Documents: {SAMPLE_CIMS_DIR}")

    # Check if API is running
    try:
        health = requests.get(f"{API_URL}/api/health", timeout=5)
        if health.status_code != 200:
            print(f"\n❌ API not healthy: {health.status_code}")
            return
        print("✅ API is running")
    except Exception as e:
        print(f"\n❌ Cannot connect to API: {e}")
        print("💡 Make sure backend is running: uvicorn app.main:app --reload")
        return

    # Get all CIM documents
    pdf_files = sorted(SAMPLE_CIMS_DIR.glob("CIM-*.pdf"))

    if not pdf_files:
        print(f"\n❌ No CIM documents found in {SAMPLE_CIMS_DIR}")
        return

    print(f"\nFound {len(pdf_files)} documents to test:\n")
    for pdf in pdf_files:
        print(f"  - {pdf.name}")

    # Test each document
    results = []
    for pdf_path in pdf_files:
        result = test_document(pdf_path)
        results.append(result)

        # Small delay between documents
        if pdf_path != pdf_files[-1]:
            time.sleep(2)

    # Summary
    print("\n" + "="*70)
    print("📊 SUMMARY")
    print("="*70)

    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    print(f"\n✅ Successful: {len(successful)}/{len(results)}")
    print(f"❌ Failed: {len(failed)}/{len(results)}")

    if successful:
        print(f"\n✅ Successful Extractions:")
        for r in successful:
            cached = " (cached)" if r.get('cached') else ""
            print(f"   {r['file']}: {r['time']:.1f}s{cached}")

    if failed:
        print(f"\n❌ Failed Extractions:")
        for r in failed:
            print(f"   {r['file']}: {r.get('error', 'Unknown error')}")

    total_time = sum(r['time'] for r in results)
    print(f"\n⏱️  Total time: {total_time:.1f}s")

    if len(successful) == len(results):
        print("\n🎉 ALL TESTS PASSED! Ready to run quality scripts.")
        print("\nNext steps:")
        print("  1. python scripts/test_extraction_quality.py --mode validate tests/data/golden_outputs/")
        print("  2. python scripts/check_extraction_coverage.py tests/data/golden_outputs/")
    else:
        print("\n⚠️  Some tests failed. Check errors above.")

    print("="*70 + "\n")


if __name__ == "__main__":
    main()
