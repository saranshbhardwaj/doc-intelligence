#!/usr/bin/env python3
"""
Quick coverage check for extraction results.
Shows which fields are being populated across multiple extractions.

Usage:
  python scripts/check_extraction_coverage.py logs/parsed/*.json
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict


def analyze_coverage(file_paths: List[Path]) -> Dict:
    """Analyze field coverage across multiple extractions"""

    coverage = defaultdict(lambda: {"count": 0, "total": 0, "percentage": 0})
    total_files = len(file_paths)

    for path in file_paths:
        try:
            data = json.loads(path.read_text())
            extracted_data = data.get("data", {})

            # Check each major section
            sections = [
                "company_info", "financials", "balance_sheet", "financial_ratios",
                "customers", "market", "key_risks", "management_team",
                "transaction_details", "growth_analysis", "valuation_multiples",
                "capital_structure", "operating_metrics", "strategic_rationale"
            ]

            for section in sections:
                section_data = extracted_data.get(section)
                coverage[section]["total"] += 1

                if section_data:
                    coverage[section]["count"] += 1

                    # Count sub-fields for detailed sections
                    if section == "financials" and isinstance(section_data, dict):
                        if section_data.get("revenue_by_year"):
                            coverage["financials.revenue"]["count"] += 1
                        coverage["financials.revenue"]["total"] += 1

                        if section_data.get("ebitda_by_year"):
                            coverage["financials.ebitda"]["count"] += 1
                        coverage["financials.ebitda"]["total"] += 1

                    elif section == "key_risks" and isinstance(section_data, list):
                        risk_count = len(section_data)
                        coverage["key_risks.count"]["count"] += risk_count
                        coverage["key_risks.count"]["total"] += 1

                    elif section == "management_team" and isinstance(section_data, list):
                        team_count = len(section_data)
                        coverage["management_team.count"]["count"] += team_count
                        coverage["management_team.count"]["total"] += 1

        except Exception as e:
            print(f"Error processing {path.name}: {e}")
            continue

    # Calculate percentages
    for field, data in coverage.items():
        if data["total"] > 0:
            data["percentage"] = round((data["count"] / data["total"]) * 100, 1)

    return dict(coverage)


def print_coverage_report(coverage: Dict, total_files: int):
    """Pretty print coverage report"""

    print(f"\n{'='*70}")
    print(f"EXTRACTION COVERAGE REPORT ({total_files} documents)")
    print(f"{'='*70}\n")

    # Sort by percentage
    sorted_fields = sorted(coverage.items(), key=lambda x: x[1]["percentage"], reverse=True)

    print(f"{'Field':<40} {'Coverage':<15} {'Status'}")
    print(f"{'-'*40} {'-'*15} {'-'*10}")

    for field, data in sorted_fields:
        percentage = data["percentage"]
        count = data["count"]
        total = data["total"]

        # Status indicator
        if percentage >= 90:
            status = "✓ Excellent"
            color = ""
        elif percentage >= 70:
            status = "⚠ Good"
            color = ""
        elif percentage >= 50:
            status = "⚠ Fair"
            color = ""
        else:
            status = "✗ Poor"
            color = ""

        # Special handling for count fields
        display_field = field
        if ".count" in field:
            avg = count / total if total > 0 else 0
            coverage_str = f"avg {avg:.1f} items"
        else:
            coverage_str = f"{count}/{total} ({percentage}%)"

        print(f"{display_field:<40} {coverage_str:<15} {status}")

    # Summary
    print(f"\n{'-'*70}")
    high_coverage = sum(1 for d in coverage.values() if d["percentage"] >= 80)
    total_fields = len(coverage)
    print(f"High coverage (≥80%): {high_coverage}/{total_fields} fields")

    # Recommendations
    print(f"\n{'='*70}")
    print("RECOMMENDATIONS:")
    print(f"{'='*70}")

    low_coverage_fields = [k for k, v in coverage.items() if v["percentage"] < 50 and v["total"] > 0]

    if low_coverage_fields:
        print("\n⚠ Fields with low coverage (< 50%):")
        for field in low_coverage_fields[:5]:  # Top 5
            print(f"  - {field}: {coverage[field]['percentage']}%")
        print("\nConsider:")
        print("  1. Checking if these fields are common in CIM documents")
        print("  2. Improving prompt instructions for these sections")
        print("  3. Adding examples in the prompt for these fields")
    else:
        print("\n✓ All fields have good coverage (≥50%)!")

    # Confidence analysis
    print(f"\n{'='*70}")
    print("NEXT STEPS:")
    print(f"{'='*70}")
    print("1. Review low-coverage fields manually in original PDFs")
    print("2. Check if missing data is due to:")
    print("   - Data not present in document (expected)")
    print("   - Prompt not clear enough (fix prompt)")
    print("   - Data in unusual format (add examples)")
    print("3. Run regression test after prompt changes")


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_extraction_coverage.py <json_files>")
        print("Example: python check_extraction_coverage.py logs/parsed/*.json")
        sys.exit(1)

    # Get file paths
    file_paths = [Path(p) for p in sys.argv[1:]]
    file_paths = [p for p in file_paths if p.exists() and p.suffix == ".json"]

    if not file_paths:
        print("Error: No valid JSON files found")
        sys.exit(1)

    print(f"Analyzing {len(file_paths)} extraction(s)...")

    coverage = analyze_coverage(file_paths)
    print_coverage_report(coverage, len(file_paths))


if __name__ == "__main__":
    main()
