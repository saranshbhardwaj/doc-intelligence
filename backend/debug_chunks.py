"""
Debug script to check what page numbers are in the document_chunks table.
This will help identify if the parser or chunker assigned the wrong page number.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.config import settings

def debug_chunks():
    """Query document_chunks to see page numbers for Price field."""

    # Database connection
    engine = create_engine(
        "postgresql://docint:docint@localhost:5433/docint",
        echo=False
    )

    print("=" * 80)
    print("DEBUGGING DOCUMENT CHUNKS - PRICE FIELD PAGE NUMBER")
    print("=" * 80)
    print()

    with engine.connect() as conn:
        # Query 1: All key_value_pairs chunks
        print("1. ALL KEY-VALUE PAIRS CHUNKS:")
        print("-" * 80)

        result = conn.execute(text("""
            SELECT
                id,
                LEFT(content, 100) as content_preview,
                metadata->>'page_number' as page_number,
                metadata->>'page_range' as page_range
            FROM document_chunks
            WHERE section_type = 'key_value_pairs'
            ORDER BY (metadata->>'page_number')::int
        """))

        for row in result:
            print(f"ID: {row[0]}")
            print(f"  Content: {row[1]}")
            print(f"  Page: {row[2]} (Range: {row[3]})")
            print()

        # Query 2: Find chunks with "Price"
        print()
        print("2. CHUNKS CONTAINING 'Price' OR '$2,500,000':")
        print("-" * 80)

        result = conn.execute(text("""
            SELECT
                id,
                section_type,
                content,
                metadata->>'page_number' as page_number,
                metadata->>'page_range' as page_range,
                metadata
            FROM document_chunks
            WHERE content ILIKE '%price%'
               OR content ILIKE '%2,500,000%'
               OR content ILIKE '%2500000%'
            ORDER BY (metadata->>'page_number')::int, id
        """))

        rows = result.fetchall()
        if not rows:
            print("❌ NO CHUNKS FOUND with 'Price' or '$2,500,000'")
            print("This means the data wasn't chunked yet, or search term is different.")
        else:
            for row in rows:
                print(f"\n📄 Chunk ID: {row[0]}")
                print(f"   Type: {row[1]}")
                print(f"   Page: {row[3]} (Range: {row[4]})")
                print(f"   Content Preview:")
                print(f"   {row[2][:500]}")
                print()

                # Check if page 3
                if row[3] == '3':
                    print("   ⚠️  THIS CHUNK SAYS PAGE 3!")
                    print("   ⚠️  But you said Price is NOT on page 3!")
                    print("   ⚠️  This means either:")
                    print("         1. Azure DI detected it on the wrong page")
                    print("         2. The PDF has hidden text/metadata on page 3")
                    print("         3. Azure DI's bounding region was incorrect")

        print()
        print("=" * 80)
        print("NEXT STEPS:")
        print("1. Manually open the PDF and search for 'Price' and '$2,500,000'")
        print("2. Note which page it's actually on")
        print("3. If the page number above is WRONG, it's an Azure DI accuracy issue")
        print("=" * 80)

if __name__ == "__main__":
    try:
        debug_chunks()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
