#!/usr/bin/env python3
"""Test script to verify normalization fixes for Investment Memo workflow.

This script tests the normalization layer against the failing LLM output
to ensure all 3 validation errors are fixed.
"""
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.verticals.private_equity.workflows.normalization import normalize_workflow_output
from app.verticals.private_equity.workflows.validator import validate_output

# The raw LLM output that was failing
RAW_LLM_OUTPUT = {
    "currency": "USD",
    "company_overview": {
        "company_name": "NPC International LLC",
        "company_id": None,
        "industry": "Restaurant Franchising",
        "secondary_industry": "Food Service",
        "business_structure": "LLC",
        "founded_year": 1962,
        "employees": None,
        "headquarters": "United States",
        "website": None,
        "provenance": {
            "section_heading": "Company Overview",
            "page_numbers": [1, 2],
            "text_excerpt": "NPC International, Inc. is the largest Pizza Hut franchisee and the largest franchisee of any restaurant concept in the United States"
        },
        "confidence": 0.9
    },
    "financials": {
        "currency": "USD",
        "fiscal_year_end": "December 31",
        "historical": [
            {
                "year": 2011,
                "revenue": 111900000,
                "ebitda": 45300000,
                "margin": 0.405,
                "citation": "[D3:p2]"
            }
        ],
        "metrics": {
            "rev_cagr": 0.017,
            "ebitda_margin_latest": 0.405,
            "citation": ["[D1:p3]"]
        }
    },
    "market": {
        "market_size_estimate": 29500000000,
        "market_growth_rate": "1.7% CAGR",
        "competitive_position": "Market Leader",
        "market_share": {
            "Pizza Hut": 0.147,
            "Domino's": 0.109,
            "Papa John's": 0.069,
            "Regionals/Independents": 0.629
        },
        "provenance": {
            "section_heading": "Market Competition",
            "page_numbers": [1, 3],
            "text_excerpt": "QSR Pizza Market Share as of Q2 2011"
        },
        "confidence": 0.85
    },
    "valuation": {
        "asking_ev_ebitda": 6.7,
        "enterprise_value": 755000000,
        "transaction_details": {
            "seller": "Olympus Partners",
            "transaction_date": "November 6, 2011",
            "deal_type": "Majority Acquisition"
        },
        "provenance": {
            "section_heading": "Transaction Overview",
            "page_numbers": [2, 3],
            "text_excerpt": "Olympus Partners signed a definitive agreement to acquire NPC Acquisition Holdings LLC for an enterprise value of approximately $755 million"
        },
        "confidence": 0.9
    },
    "risks": [
        {
            "risk": "Customer Concentration",  # Wrong field name
            "severity": "Medium",
            "description": "Potential dependency on limited number of customers or markets",
            "inferred": True,  # Extra field
            "confidence": 0.6  # Extra field
            # Missing "category"
        },
        {
            "risk": "Franchise Dependency",  # Wrong field name
            "severity": "Medium",
            "description": "Reliance on Pizza Hut brand and franchise agreement",
            "inferred": True,  # Extra field
            "confidence": 0.7  # Extra field
            # Missing "category"
        }
    ],
    "opportunities": [
        {
            "description": "Geographic expansion across 28 states",
            "category": "Growth",
            "impact": "High",
            "citations": ["[D1:p2]"]
        },
        {
            "description": "Potential for menu diversification with WingStreet product line",
            "category": "Product",
            "impact": "Medium",
            "citations": ["[D1:p4]"]
        }
    ],
    "sections": [  # Only 1 section - schema requires minItems: 2
        {
            "key": "executive_overview",
            "title": "Executive Overview",
            "content": "### Investment Highlights\\n\\n**Company:** NPC International is the largest Pizza Hut franchisee globally, operating 1,153 locations across 28 US states [D1:p2].\\n\\n**Financial Performance:** 2011 revenue reached $111.9M with EBITDA of $45.3M (40.5% margin) [D3:p2].\\n\\n**Market Position:**\\n- Largest Pizza Hut franchisee in the world\\n- Operates in 28 states with diverse geographic coverage\\n- Strong unit economics with significant market presence\\n\\n**Key Risks:**\\n- Customer concentration\\n- Franchise dependency\\n\\n**Investment Thesis:** The company presents a compelling opportunity due to its market leadership, proven track record, and clear path to operational improvements.",
            "citations": ["[D1:p2]", "[D3:p2]"],
            "confidence": 0.9
        }
    ],
    "next_steps": [
        {
            "priority": 1,
            "action": "Conduct detailed financial due diligence",
            "owner": "Investor",
            "timeline_days": 30
        },
        {
            "priority": 2,
            "action": "Review franchise agreement terms",
            "owner": "Legal Team",
            "timeline_days": 21
        }
    ],
    "extraction_notes": "Data extracted from 2011 transaction document. Limited current financial information available. Recommend updating with more recent financial data.",
    "meta": {
        "version": 2
    }
    # Missing "references" field - required by schema
}


def test_normalization():
    """Test that normalization fixes all 3 validation errors."""
    print("=" * 80)
    print("TESTING NORMALIZATION FIXES")
    print("=" * 80)
    print()

    # Show original issues
    print("ORIGINAL LLM OUTPUT ISSUES:")
    print("1. Missing 'references' field (required)")
    print(f"2. Only {len(RAW_LLM_OUTPUT['sections'])} section (schema requires minItems: 2)")
    print(f"3. Risk items have wrong structure:")
    for i, risk in enumerate(RAW_LLM_OUTPUT['risks']):
        print(f"   Risk {i+1}: {list(risk.keys())}")
        print(f"   - Has 'risk' field instead of using 'description' properly")
        print(f"   - Missing 'category' field")
        print(f"   - Has extra fields: 'inferred', 'confidence'")
    print()

    # Validate before normalization
    print("VALIDATION BEFORE NORMALIZATION:")
    print("-" * 80)
    validation_before = validate_output("Investment Memo", RAW_LLM_OUTPUT)
    print(f"Valid: {validation_before.valid}")
    print(f"Schema Applied: {validation_before.schema_applied}")
    if validation_before.errors:
        print(f"Errors ({len(validation_before.errors)}):")
        for error in validation_before.errors:
            print(f"  - [{error.code}] {error.message}")
            if error.path:
                print(f"    Path: {' -> '.join(str(p) for p in error.path)}")
    print()

    # Apply normalization
    print("APPLYING NORMALIZATION...")
    print("-" * 80)
    normalized = normalize_workflow_output(RAW_LLM_OUTPUT, "Investment Memo", currency="USD")
    print(f"✓ Normalization complete")
    print()

    # Check fixes
    print("NORMALIZATION FIXES APPLIED:")
    print("-" * 80)
    print(f"✓ Added 'references' field: {len(normalized.get('references', []))} citations")
    print(f"✓ Sections count: {len(normalized.get('sections', []))} (minimum 2)")
    print(f"✓ Risk items normalized:")
    for i, risk in enumerate(normalized.get('risks', [])):
        print(f"   Risk {i+1}: {list(risk.keys())}")
    print()

    # Validate after normalization
    print("VALIDATION AFTER NORMALIZATION:")
    print("-" * 80)
    validation_after = validate_output("Investment Memo", normalized)
    print(f"Valid: {validation_after.valid}")
    print(f"Schema Applied: {validation_after.schema_applied}")
    if validation_after.errors:
        print(f"Errors ({len(validation_after.errors)}):")
        for error in validation_after.errors:
            print(f"  - [{error.code}] {error.message}")
            if error.path:
                print(f"    Path: {' -> '.join(str(p) for p in error.path)}")
    else:
        print("✓ NO ERRORS - Validation passed!")
    print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    errors_before = len(validation_before.errors)
    errors_after = len(validation_after.errors)
    print(f"Errors before: {errors_before}")
    print(f"Errors after:  {errors_after}")
    print(f"Errors fixed:  {errors_before - errors_after}")
    print()

    if validation_after.valid:
        print("✅ SUCCESS! All validation errors fixed by normalization.")
        return True
    else:
        print("❌ FAILURE! Some validation errors remain.")
        return False


if __name__ == "__main__":
    success = test_normalization()
    sys.exit(0 if success else 1)
