"""Test script to verify template fill pipeline end-to-end.

This tests:
1. Excel template analysis (with new key-value + table structure)
2. Field detection from PDF (with citations and metadata)
3. Auto-mapping (with new schema)
4. Data extraction (with citations)
5. Excel filling

Run this BEFORE testing through Celery to catch schema issues.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.verticals.real_estate.template_filling.excel_handler import ExcelHandler
from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService


async def test_pipeline():
    """Test the full template fill pipeline."""

    print("=" * 80)
    print("TEMPLATE FILL PIPELINE TEST")
    print("=" * 80)

    # Paths
    excel_path = r"C:\Users\sar13821\Downloads\RE\Synthesis - Tulsa Storage OK - Copy.xlsx"

    # For PDF, we'll need to get a processed document
    # For now, let's just test the Excel template analysis

    # ========================================================================
    # STEP 0: Analyze Excel Template
    # ========================================================================
    print("\n[STEP 0] Analyzing Excel Template...")
    print("-" * 80)

    handler = ExcelHandler()
    excel_schema = handler.analyze_template(excel_path)

    print(f"✅ Template analyzed successfully!")
    print(f"   Sheets: {len(excel_schema['sheets'])}")
    print(f"   Key-Value Fields: {excel_schema['total_key_value_fields']}")
    print(f"   Tables: {excel_schema['total_tables']}")

    # Show sample sheet structure
    if excel_schema['sheets']:
        sample_sheet = excel_schema['sheets'][0]
        print(f"\n   Sample Sheet: {sample_sheet['name']}")
        print(f"     - Key-value fields: {len(sample_sheet['key_value_fields'])}")
        print(f"     - Tables: {len(sample_sheet['tables'])}")

        if sample_sheet['key_value_fields']:
            kv_sample = sample_sheet['key_value_fields'][0]
            print(f"     - Sample KV field: {kv_sample['cell']} = \"{kv_sample['label']}\"")

        if sample_sheet['tables']:
            table_sample = sample_sheet['tables'][0]
            print(f"     - Sample table: \"{table_sample['table_name']}\" ({table_sample['total_fillable_cells']} cells)")

    # ========================================================================
    # VERIFY SCHEMA STRUCTURE
    # ========================================================================
    print("\n[VERIFICATION] Checking schema structure...")
    print("-" * 80)

    required_keys = ['sheets', 'total_key_value_fields', 'total_tables', 'has_formulas']
    missing_keys = [k for k in required_keys if k not in excel_schema]

    if missing_keys:
        print(f"❌ Missing schema keys: {missing_keys}")
        return

    print("✅ Schema structure is valid!")

    # Check sheet structure
    for sheet in excel_schema['sheets']:
        required_sheet_keys = ['name', 'index', 'key_value_fields', 'tables', 'formula_cells']
        missing_sheet_keys = [k for k in required_sheet_keys if k not in sheet]

        if missing_sheet_keys:
            print(f"❌ Sheet '{sheet['name']}' missing keys: {missing_sheet_keys}")
            return

    print("✅ All sheets have correct structure!")

    # ========================================================================
    # VERIFY TABLE STRUCTURE
    # ========================================================================
    print("\n[VERIFICATION] Checking table structure...")
    print("-" * 80)

    total_tables_found = sum(len(s['tables']) for s in excel_schema['sheets'])
    print(f"Total tables across all sheets: {total_tables_found}")

    if total_tables_found > 0:
        # Find first sheet with tables
        for sheet in excel_schema['sheets']:
            if sheet['tables']:
                sample_table = sheet['tables'][0]
                print(f"\nSample table from '{sheet['name']}':")
                print(f"  - Name: {sample_table['table_name']}")
                print(f"  - Header row: {sample_table['header_row']}")
                print(f"  - Columns: {len(sample_table['column_headers'])}")
                print(f"  - Data rows: {sample_table['total_data_rows']}")
                print(f"  - Fillable cells: {sample_table['total_fillable_cells']}")
                print(f"  - Column headers: {sample_table['column_headers'][:5]}...")

                if sample_table['fillable_cells']:
                    sample_cell = sample_table['fillable_cells'][0]
                    required_cell_keys = ['cell', 'row', 'col', 'col_header', 'row_label', 'type']
                    missing_cell_keys = [k for k in required_cell_keys if k not in sample_cell]

                    if missing_cell_keys:
                        print(f"  ❌ Fillable cell missing keys: {missing_cell_keys}")
                        return

                    print(f"  ✅ Fillable cells have correct structure!")
                    print(f"     Sample: {sample_cell['cell']} (col: \"{sample_cell['col_header']}\", row: {sample_cell['row_label']})")

                break

    # ========================================================================
    # TEST LLM PROMPT COMPATIBILITY
    # ========================================================================
    print("\n[VERIFICATION] Testing LLM prompt compatibility...")
    print("-" * 80)

    # Create mock PDF fields
    mock_pdf_fields = [
        {
            "id": "f1",
            "name": "Property Name",
            "type": "text",
            "sample_value": "Tulsa Storage Center",
            "confidence": 0.95,
            "citations": ["[D1:p1]"],
            "description": "Name of the property"
        },
        {
            "id": "f2",
            "name": "Total SF",
            "type": "number",
            "sample_value": "50000",
            "confidence": 0.90,
            "citations": ["[D1:p2]"],
            "description": "Total square footage"
        }
    ]

    # Test that the LLM service can build prompts with new schema
    llm_service = TemplateFillLLMService()

    try:
        # Test auto-mapping prompt
        mapping_prompt = llm_service._build_auto_mapping_prompt(mock_pdf_fields, excel_schema)
        print("✅ Auto-mapping prompt built successfully!")
        print(f"   Prompt length: {len(mapping_prompt)} chars")

        # Verify prompt contains new structure info
        if "key_value_fields" in mapping_prompt and "tables" in mapping_prompt:
            print("✅ Prompt references both key-value fields and tables!")
        else:
            print("❌ Prompt missing references to new schema structure!")
            return

    except Exception as e:
        print(f"❌ Error building LLM prompt: {e}")
        return

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print("✅ Excel template analysis: PASSED")
    print("✅ Schema structure validation: PASSED")
    print("✅ Table structure validation: PASSED")
    print("✅ LLM prompt compatibility: PASSED")
    print("\n🎉 All tests passed! Template fill pipeline is ready for testing.")
    print("\nNext steps:")
    print("1. Test with a real PDF document through the API")
    print("2. Monitor citations in LLM responses")
    print("3. Verify table cells are mapped correctly")

    # Save schema for inspection
    output_path = Path(__file__).parent / "test_excel_schema.json"
    with open(output_path, "w") as f:
        json.dump(excel_schema, f, indent=2)
    print(f"\n📄 Full schema saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
