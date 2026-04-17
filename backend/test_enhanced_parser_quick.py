"""Quick test for enhanced Azure parser - prints structure summary."""
import asyncio
import sys
from app.core.parsers.azure_document_intelligence_parser import AzureDocumentIntelligenceParser


async def quick_test(pdf_path: str):
    """Quick test of enhanced parser."""
    print(f"\n📄 Testing Enhanced Parser")
    print(f"   File: {pdf_path}")
    print("=" * 60)

    parser = AzureDocumentIntelligenceParser()

    try:
        result = await parser.parse(pdf_path, pdf_type="digital")

        # Basic info
        print(f"\n✅ Parsed successfully!")
        print(f"   Pages: {result.page_count}")
        print(f"   Time: {result.processing_time_ms}ms")

        # Structure summary
        metadata = result.metadata
        doc_structure = metadata.get("document_structure", {})

        print(f"\n📊 Document Structure:")
        print(f"   Paragraphs: {doc_structure.get('total_paragraphs', 0)}")
        print(f"   Sections: {doc_structure.get('total_sections', 0)}")
        print(f"   Figures: {doc_structure.get('total_figures', 0)}")
        print(f"   Tables: {metadata.get('total_tables', 0)}")

        # Paragraph roles
        print(f"\n📝 Paragraph Roles:")
        roles = doc_structure.get("paragraph_roles", {})
        for role, count in sorted(roles.items(), key=lambda x: -x[1]):
            print(f"   - {role:20} {count:3}")

        # Sample headings
        enhanced_pages = metadata.get("enhanced_pages", [])
        all_headings = []
        for page in enhanced_pages:
            all_headings.extend(page.get("section_headings", []))

        if all_headings:
            print(f"\n📌 Section Headings (first 5):")
            for heading in all_headings[:5]:
                print(f"   - {heading}")

        print("\n" + "=" * 60)
        print("✅ Enhanced parser is working!")
        print("✨ Ready for smart chunking!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_enhanced_parser_quick.py <pdf_path>")
        sys.exit(1)

    asyncio.run(quick_test(sys.argv[1]))
