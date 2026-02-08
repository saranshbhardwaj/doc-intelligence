"""Comprehensive test for smart chunking pipeline.

Tests the complete flow:
1. Enhanced Azure parser (with structured data extraction)
2. Smart chunker (section-based with size limits)
3. Metadata population and relationships
"""
import asyncio
import sys
from pathlib import Path
from typing import Dict, List
from app.core.parsers.azure_document_intelligence_parser import AzureDocumentIntelligenceParser
from app.core.chunkers.azure_smart_chunker import AzureSmartChunker


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough heuristic: 4 chars ≈ 1 token)."""
    return len(text) // 4


def print_section_header(title: str, char: str = "="):
    """Print a formatted section header."""
    print(f"\n{char * 70}")
    print(f" {title}")
    print(f"{char * 70}")


def print_chunk_summary(chunks: List[Dict], chunk_type: str = "All"):
    """Print summary statistics for chunks."""
    print(f"\n📊 {chunk_type} Chunk Statistics:")
    print(f"   Total chunks: {len(chunks)}")

    if not chunks:
        return

    # Token statistics
    token_counts = [estimate_tokens(c.text) for c in chunks]
    print(f"   Token counts:")
    print(f"     - Min: {min(token_counts)}")
    print(f"     - Max: {max(token_counts)}")
    print(f"     - Avg: {sum(token_counts) // len(token_counts)}")

    # Continuation chunks
    continuation_count = sum(1 for c in chunks if c.metadata and c.metadata.get("is_continuation"))
    print(f"   Continuation chunks: {continuation_count}")

    # Chunks with relationships
    with_parent = sum(1 for c in chunks if c.metadata and c.metadata.get("parent_chunk_id"))
    with_siblings = sum(1 for c in chunks if c.metadata and c.metadata.get("sibling_chunk_ids"))
    with_linked = sum(1 for c in chunks if c.metadata and (
        c.metadata.get("linked_narrative_id") or c.metadata.get("linked_table_ids")
    ))
    print(f"   Chunks with parent: {with_parent}")
    print(f"   Chunks with siblings: {with_siblings}")
    print(f"   Chunks with links: {with_linked}")


def print_chunk_details(chunk: Dict, index: int):
    """Print detailed information about a single chunk."""
    print(f"\n{'─' * 70}")
    print(f"Chunk #{index + 1}")
    print(f"{'─' * 70}")

    # Basic info
    print(f"Type: {chunk.chunk_type}")
    print(f"Page: {chunk.page_number}")
    print(f"Tokens (estimated): {estimate_tokens(chunk.text)}")

    # Text preview
    text_preview = chunk.text[:200].replace('\n', ' ')
    if len(chunk.text) > 200:
        text_preview += "..."
    print(f"\nText preview:")
    print(f"  {text_preview}")

    # Metadata
    if chunk.metadata:
        print(f"\n📋 Metadata:")
        metadata = chunk.metadata

        # Section info
        if metadata.get("section_id"):
            print(f"  Section ID: {metadata['section_id']}")

        # Heading hierarchy
        if metadata.get("heading_hierarchy"):
            hierarchy = " → ".join(metadata["heading_hierarchy"])
            print(f"  Headings: {hierarchy}")

        # Sequence info
        if metadata.get("is_continuation"):
            seq = metadata.get("chunk_sequence", "?")
            total = metadata.get("total_chunks_in_section", "?")
            print(f"  ⚠️  Continuation: {seq}/{total}")

        # Relationships
        if metadata.get("parent_chunk_id"):
            print(f"  Parent: {metadata['parent_chunk_id']}")

        if metadata.get("sibling_chunk_ids"):
            siblings = metadata["sibling_chunk_ids"]
            print(f"  Siblings: {len(siblings)} chunks")

        if metadata.get("linked_narrative_id"):
            print(f"  🔗 Linked to narrative: {metadata['linked_narrative_id']}")

        if metadata.get("linked_table_ids"):
            tables = metadata["linked_table_ids"]
            print(f"  🔗 Linked to tables: {len(tables)} tables")

        # Table-specific metadata
        if chunk.chunk_type == "table":
            if metadata.get("table_caption"):
                print(f"  Caption: {metadata['table_caption']}")
            if metadata.get("table_context"):
                context = metadata["table_context"][:100]
                if len(metadata.get("table_context", "")) > 100:
                    context += "..."
                print(f"  Context: {context}")
            if metadata.get("table_row_count"):
                print(f"  Dimensions: {metadata['table_row_count']}×{metadata.get('table_column_count', '?')}")

        # Paragraph roles
        if metadata.get("paragraph_roles"):
            roles = ", ".join(metadata["paragraph_roles"])
            print(f"  Paragraph roles: {roles}")

    # Tables (if narrative chunk with tables)
    if chunk.tables and chunk.chunk_type == "narrative":
        print(f"\n📋 Contains {len(chunk.tables)} table(s) (stored separately)")


def analyze_relationships(chunks: List[Dict]):
    """Analyze and print chunk relationship patterns."""
    print_section_header("Chunk Relationship Analysis", "─")

    # Group chunks by section
    sections = {}
    for chunk in chunks:
        if not chunk.metadata:
            continue
        section_id = chunk.metadata.get("section_id")
        if section_id:
            if section_id not in sections:
                sections[section_id] = []
            sections[section_id].append(chunk)

    print(f"\n📑 Sections identified: {len(sections)}")

    for section_id, section_chunks in sections.items():
        # Find narrative chunks in this section
        narrative_chunks = [c for c in section_chunks if c.chunk_type == "narrative"]
        table_chunks = [c for c in section_chunks if c.chunk_type == "table"]

        # Get section heading
        heading = "Unknown"
        if narrative_chunks and narrative_chunks[0].chunk_metadata:
            hierarchy = narrative_chunks[0].chunk_metadata.get("heading_hierarchy", [])
            if hierarchy:
                heading = hierarchy[-1]  # Last heading in hierarchy

        print(f"\n  Section: {heading}")
        print(f"    ID: {section_id}")
        print(f"    Narrative chunks: {len(narrative_chunks)}")
        print(f"    Table chunks: {table_chunks}")

        # Check for continuations
        continuation_chunks = [c for c in narrative_chunks
                              if c.metadata and c.metadata.get("is_continuation")]
        if continuation_chunks:
            print(f"    ⚠️  Split into {len(narrative_chunks)} continuation chunks")
            for i, chunk in enumerate(narrative_chunks):
                tokens = estimate_tokens(chunk.text)
                seq = chunk.metadata.get("chunk_sequence", i+1)
                print(f"      Part {seq}: ~{tokens} tokens")


def validate_chunk_constraints(chunks: List[Dict], max_tokens: int = 500) -> List[str]:
    """Validate that chunks meet expected constraints."""
    issues = []

    print_section_header("Validation", "─")

    # Check token limits for narrative chunks
    oversized = []
    for i, chunk in enumerate(chunks):
        if chunk.chunk_type == "narrative":
            tokens = estimate_tokens(chunk.text)
            if tokens > max_tokens:
                oversized.append((i, tokens))

    if oversized:
        issues.append(f"Found {len(oversized)} narrative chunks over {max_tokens} tokens")
        for idx, tokens in oversized[:3]:  # Show first 3
            print(f"  ⚠️  Chunk #{idx + 1}: {tokens} tokens (exceeds {max_tokens})")
    else:
        print(f"  ✅ All narrative chunks under {max_tokens} token limit")

    # Check metadata presence
    chunks_without_metadata = [i for i, c in enumerate(chunks)
                               if not c.metadata]
    if chunks_without_metadata:
        issues.append(f"Found {len(chunks_without_metadata)} chunks without metadata")
        print(f"  ⚠️  {len(chunks_without_metadata)} chunks missing metadata")
    else:
        print(f"  ✅ All chunks have metadata")

    # Check table-narrative linking
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    unlinked_tables = [c for c in table_chunks
                      if not c.metadata or not c.metadata.get("linked_narrative_id")]
    if unlinked_tables:
        issues.append(f"Found {len(unlinked_tables)} tables not linked to narrative")
        print(f"  ⚠️  {len(unlinked_tables)} tables not linked to narrative")
    else:
        if table_chunks:
            print(f"  ✅ All {len(table_chunks)} tables linked to narrative")

    # Check continuation chain integrity
    continuation_chunks = [c for c in chunks
                          if c.metadata and c.metadata.get("is_continuation")]
    for chunk in continuation_chunks:
        parent_id = chunk.metadata.get("parent_chunk_id")
        if not parent_id:
            issues.append(f"Continuation chunk missing parent_chunk_id")
            print(f"  ⚠️  Continuation chunk missing parent reference")
            break
    else:
        if continuation_chunks:
            print(f"  ✅ All {len(continuation_chunks)} continuation chunks have parent references")

    if not issues:
        print("\n  🎉 All validation checks passed!")

    return issues


async def test_pipeline(pdf_path: str, show_all_chunks: bool = False):
    """Test the complete smart chunking pipeline."""
    print("=" * 70)
    print(" SMART CHUNKING PIPELINE TEST")
    print("=" * 70)
    print(f"\n📄 Document: {pdf_path}")

    # Step 1: Parse with enhanced parser
    print_section_header("Step 1: Enhanced Parsing")
    parser = AzureDocumentIntelligenceParser()

    try:
        print("Parsing document with Azure Document Intelligence...")
        parser_output = await parser.parse(pdf_path, pdf_type="digital")
        print(f"✅ Parsed successfully!")
        print(f"   Parser: {parser_output.parser_name} v{parser_output.parser_version}")
        print(f"   Pages: {parser_output.page_count}")
        print(f"   Time: {parser_output.processing_time_ms}ms")

        # Show structure summary
        metadata = parser_output.metadata
        doc_structure = metadata.get("document_structure", {})
        print(f"\n📊 Document Structure:")
        print(f"   Paragraphs: {doc_structure.get('total_paragraphs', 0)}")
        print(f"   Sections: {doc_structure.get('total_sections', 0)}")
        print(f"   Tables: {metadata.get('total_tables', 0)}")
        print(f"   Figures: {doc_structure.get('total_figures', 0)}")

        # Paragraph roles
        roles = doc_structure.get("paragraph_roles", {})
        if roles:
            print(f"\n   Paragraph roles:")
            for role, count in sorted(roles.items(), key=lambda x: -x[1]):
                print(f"     - {role}: {count}")

    except Exception as e:
        print(f"❌ Parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 2: Chunk with smart chunker
    print_section_header("Step 2: Smart Chunking")
    chunker = AzureSmartChunker(max_tokens=500)

    try:
        print("Chunking with section-based smart chunker...")
        chunking_output = chunker.chunk(parser_output)
        chunks = chunking_output.chunks
        print(f"✅ Chunked successfully!")
        print(f"   Total chunks: {len(chunks)}")
        print(f"   Processing time: {chunking_output.processing_time_ms}ms")

    except Exception as e:
        print(f"❌ Chunking failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 3: Analyze results
    print_section_header("Step 3: Results Analysis")

    # Separate by type
    narrative_chunks = [c for c in chunks if c.chunk_type == "narrative"]
    table_chunks = [c for c in chunks if c.chunk_type == "table"]

    print_chunk_summary(narrative_chunks, "Narrative")
    print_chunk_summary(table_chunks, "Table")

    # Relationship analysis
    analyze_relationships(chunks)

    # Validation
    validation_issues = validate_chunk_constraints(chunks, max_tokens=500)

    # Step 4: Show sample chunks
    print_section_header("Step 4: Sample Chunks")

    if show_all_chunks:
        print("\n📄 All Chunks:")
        for i, chunk in enumerate(chunks):
            print_chunk_details(chunk, i)
    else:
        # Show first 3 narrative chunks
        print("\n📝 First 3 Narrative Chunks:")
        for i, chunk in enumerate(narrative_chunks[:3]):
            chunk_idx = chunks.index(chunk)
            print_chunk_details(chunk, chunk_idx)

        # Show first 2 table chunks
        if table_chunks:
            print("\n\n📋 First 2 Table Chunks:")
            for i, chunk in enumerate(table_chunks[:2]):
                chunk_idx = chunks.index(chunk)
                print_chunk_details(chunk, chunk_idx)

        # Show a continuation chunk if exists
        continuation_chunks = [c for c in chunks
                              if c.metadata and c.metadata.get("is_continuation")]
        if continuation_chunks:
            print("\n\n⚠️  Sample Continuation Chunk:")
            chunk = continuation_chunks[0]
            chunk_idx = chunks.index(chunk)
            print_chunk_details(chunk, chunk_idx)

    # Final summary
    print_section_header("Test Complete!")
    print(f"\n✅ Pipeline executed successfully!")
    print(f"📊 Summary:")
    print(f"   - Parsed {parser_output.page_count} pages")
    print(f"   - Created {len(chunks)} total chunks")
    print(f"   - {len(narrative_chunks)} narrative, {len(table_chunks)} tables")
    if validation_issues:
        print(f"   - ⚠️  {len(validation_issues)} validation issues found")
    else:
        print(f"   - ✅ All validation checks passed")

    print("\n💡 Next steps:")
    print("   1. Review chunk quality and metadata")
    print("   2. Test with various document types")
    print("   3. Integrate with database storage")
    print("   4. Test retrieval with chunk relationships")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_smart_chunking_pipeline.py <pdf_path> [--show-all]")
        print("\nOptions:")
        print("  --show-all    Show all chunks instead of just samples")
        sys.exit(1)

    pdf_path = sys.argv[1]
    show_all = "--show-all" in sys.argv

    if not Path(pdf_path).exists():
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)

    asyncio.run(test_pipeline(pdf_path, show_all_chunks=show_all))
