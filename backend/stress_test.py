# backend/stress_test.py
import asyncio
import aiohttp
import time
from pathlib import Path
import statistics

async def upload_document(session, url, pdf_path, request_num):
    """Upload a single document"""
    start_time = time.time()
    
    try:
        with open(pdf_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=pdf_path.name, content_type='application/pdf')
            
            async with session.post(f"{url}/api/extract", data=data, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                elapsed = time.time() - start_time
                status = resp.status
                
                if status == 200:
                    result = await resp.json()
                    from_cache = result.get('from_cache', False)
                    print(f"✅ Request {request_num}: {status} in {elapsed:.2f}s {'(cached)' if from_cache else '(processed)'}")
                    return {'success': True, 'time': elapsed, 'status': status, 'cached': from_cache}
                else:
                    error_text = await resp.text()
                    print(f"❌ Request {request_num}: {status} in {elapsed:.2f}s - {error_text[:100]}")
                    return {'success': False, 'time': elapsed, 'status': status, 'error': error_text[:100]}
                    
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        print(f"⏱️  Request {request_num}: TIMEOUT after {elapsed:.2f}s")
        return {'success': False, 'time': elapsed, 'status': 'timeout'}
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"💥 Request {request_num}: ERROR after {elapsed:.2f}s - {str(e)}")
        return {'success': False, 'time': elapsed, 'status': 'error', 'error': str(e)}


async def stress_test(url, pdf_path, concurrent_requests=10, total_requests=50):
    """
    Run stress test with concurrent requests.
    
    Args:
        url: Base URL of API (e.g., http://localhost:8000)
        pdf_path: Path to test PDF file
        concurrent_requests: Number of simultaneous requests
        total_requests: Total number of requests to make
    """
    print(f"\n{'='*60}")
    print(f"🚀 Starting Stress Test")
    print(f"{'='*60}")
    print(f"Target: {url}")
    print(f"PDF: {pdf_path}")
    print(f"Concurrent: {concurrent_requests}")
    print(f"Total requests: {total_requests}")
    print(f"{'='*60}\n")
    
    results = []
    start_time = time.time()
    
    # Create session with connection pooling
    connector = aiohttp.TCPConnector(limit=concurrent_requests)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Process in batches
        for batch_start in range(0, total_requests, concurrent_requests):
            batch_end = min(batch_start + concurrent_requests, total_requests)
            batch_size = batch_end - batch_start
            
            print(f"\n📦 Batch {batch_start//concurrent_requests + 1}: Requests {batch_start+1}-{batch_end}")
            
            # Create tasks for this batch
            tasks = [
                upload_document(session, url, pdf_path, i+1)
                for i in range(batch_start, batch_end)
            ]
            
            # Run batch concurrently
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            
            # Small delay between batches to avoid overwhelming server
            if batch_end < total_requests:
                await asyncio.sleep(1)
    
    total_time = time.time() - start_time
    
    # Calculate statistics
    print(f"\n{'='*60}")
    print(f"📊 Results Summary")
    print(f"{'='*60}")
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    cached = [r for r in results if r.get('cached', False)]
    
    print(f"\n✅ Successful: {len(successful)}/{total_requests} ({len(successful)/total_requests*100:.1f}%)")
    print(f"❌ Failed: {len(failed)}/{total_requests} ({len(failed)/total_requests*100:.1f}%)")
    print(f"⚡ Cached: {len(cached)}/{len(successful)} ({len(cached)/len(successful)*100:.1f}% of successful)")
    
    if successful:
        times = [r['time'] for r in successful]
        print(f"\n⏱️  Response Times:")
        print(f"   Min: {min(times):.2f}s")
        print(f"   Max: {max(times):.2f}s")
        print(f"   Mean: {statistics.mean(times):.2f}s")
        print(f"   Median: {statistics.median(times):.2f}s")
    
    if failed:
        print(f"\n❌ Failure Breakdown:")
        status_counts = {}
        for r in failed:
            status = r.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        for status, count in status_counts.items():
            print(f"   {status}: {count}")
    
    print(f"\n⏱️  Total test time: {total_time:.2f}s")
    print(f"📈 Throughput: {total_requests/total_time:.2f} requests/second")
    print(f"{'='*60}\n")


async def quick_test(url, pdf_path):
    """Quick sanity check with a single request"""
    print("\n🔍 Running quick sanity check...")
    
    connector = aiohttp.TCPConnector()
    async with aiohttp.ClientSession(connector=connector) as session:
        result = await upload_document(session, url, pdf_path, 1)
        
        if result['success']:
            print(f"✅ Quick test passed! ({result['time']:.2f}s)")
            return True
        else:
            print(f"❌ Quick test failed!")
            return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Stress test the Doc Intelligence API')
    parser.add_argument('--url', default='http://localhost:8000', help='API base URL')
    parser.add_argument('--pdf', required=True, help='Path to test PDF file')
    parser.add_argument('--concurrent', type=int, default=5, help='Concurrent requests')
    parser.add_argument('--total', type=int, default=20, help='Total requests')
    parser.add_argument('--quick', action='store_true', help='Run quick test only')
    
    args = parser.parse_args()
    
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌ Error: PDF file not found: {pdf_path}")
        exit(1)
    
    if args.quick:
        asyncio.run(quick_test(args.url, pdf_path))
    else:
        asyncio.run(stress_test(
            url=args.url,
            pdf_path=pdf_path,
            concurrent_requests=args.concurrent,
            total_requests=args.total
        ))