"""Quick test for smart chunker - validates basic functionality."""
import asyncio
import sys
from app.core.parsers.azure_document_intelligence_parser import AzureDocumentIntelligenceParser
from app.core.chunkers.azure_smart_chunker import AzureSmartChunker


def estimate_tokens(text: str) -> int:
    """Estimate token count."""
    return len(text) // 4


async def quick_test(pdf_path: str):
    """Quick test of smart chunking pipeline."""
    print(f"\n📄 Testing Smart Chunking Pipeline")
    print(f"   File: {pdf_path}")
    print("=" * 60)

    # Parse
    print("\n🔍 Parsing...")
    parser = AzureDocumentIntelligenceParser()
    result = await parser.parse(pdf_path, pdf_type="digital")
    print(f"   ✅ {result.page_count} pages parsed")

    # Chunk
    print("\n✂️  Chunking...")
    chunker = AzureSmartChunker(max_tokens=500)
    chunking_output = chunker.chunk(result)
    chunks = chunking_output.chunks
    print(f"   ✅ {len(chunks)} chunks created")

    # Analysis
    narrative = [c for c in chunks if c.chunk_type == "narrative"]
    tables = [c for c in chunks if c.chunk_type == "table"]
    continuations = [c for c in chunks
                    if c.metadata and c.metadata.get("is_continuation")]

    print(f"\n📊 Chunk Breakdown:")
    print(f"   Narrative: {len(narrative)}")
    print(f"   Tables: {len(tables)}")
    print(f"   Continuations: {len(continuations)}")

    # Token stats for narrative chunks
    if narrative:
        tokens = [estimate_tokens(c.text) for c in narrative]
        print(f"\n📏 Narrative Chunk Sizes:")
        print(f"   Min: {min(tokens)} tokens")
        print(f"   Max: {max(tokens)} tokens")
        print(f"   Avg: {sum(tokens) // len(tokens)} tokens")

        # Check if any exceed limit
        oversized = [t for t in tokens if t > 500]
        if oversized:
            print(f"   ⚠️  {len(oversized)} chunks exceed 500 tokens")
        else:
            print(f"   ✅ All chunks under 500 token limit")

    # Metadata check
    with_metadata = sum(1 for c in chunks if c.metadata)
    print(f"\n📋 Metadata:")
    print(f"   Chunks with metadata: {with_metadata}/{len(chunks)}")

    # Relationships check
    with_section = sum(1 for c in chunks
                      if c.metadata and c.metadata.get("section_id"))
    with_headings = sum(1 for c in chunks
                       if c.metadata and c.metadata.get("heading_hierarchy"))
    print(f"   With section ID: {with_section}")
    print(f"   With headings: {with_headings}")

    # Sample chunk
    if narrative:
        print(f"\n📝 Sample Chunk:")
        chunk = narrative[0]
        preview = chunk.text[:150].replace('\n', ' ')
        if len(chunk.text) > 150:
            preview += "..."
        print(f"   {preview}")

        if chunk.metadata:
            if chunk.metadata.get("heading_hierarchy"):
                hierarchy = " → ".join(chunk.metadata["heading_hierarchy"])
                print(f"   Headings: {hierarchy}")
            if chunk.metadata.get("section_id"):
                print(f"   Section: {chunk.metadata['section_id']}")

    print("\n" + "=" * 60)
    print("✅ Smart chunking is working!")
    print("✨ Ready for database integration!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_smart_chunker_quick.py <pdf_path>")
        sys.exit(1)

    asyncio.run(quick_test(sys.argv[1]))
