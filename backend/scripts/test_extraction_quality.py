#!/usr/bin/env python3
"""
Test extraction quality against golden dataset.
Usage:
  python scripts/test_extraction_quality.py --mode=validate  # No API calls, just validate structure
  python scripts/test_extraction_quality.py --mode=compare   # Compare new extraction to golden
  python scripts/test_extraction_quality.py --mode=generate  # Generate new golden dataset (costs money!)
"""

import json
import sys
from pathlib import Path
from typing import Dict, List
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import ExtractedData
from pydantic import ValidationError


class ExtractionTester:
    def __init__(self, test_data_dir: Path = Path("tests/data")):
        self.test_data_dir = test_data_dir
        self.golden_dir = test_data_dir / "golden_outputs"
        self.sample_cims_dir = test_data_dir / "sample_cims"

    def validate_structure(self, output_path: Path) -> Dict:
        """Validate that output matches Pydantic models (no API call)"""
        print(f"\n{'='*60}")
        print(f"Validating: {output_path.name}")
        print(f"{'='*60}")

        try:
            data = json.loads(output_path.read_text())

            # Validate against Pydantic model
            extracted = ExtractedData(**data["data"])

            # Check completeness
            results = {
                "valid": True,
                "file": output_path.name,
                "checks": {}
            }

            # Required fields check
            required_sections = [
                "company_info", "financials", "key_risks",
                "management_team", "transaction_details"
            ]

            for section in required_sections:
                value = getattr(extracted, section, None)
                has_data = value is not None
                results["checks"][section] = {
                    "present": has_data,
                    "status": "✓" if has_data else "✗"
                }

            # Financial data completeness
            if extracted.financials:
                revenue_years = len(extracted.financials.revenue_by_year or {})
                results["checks"]["revenue_data"] = {
                    "years": revenue_years,
                    "status": "✓" if revenue_years >= 3 else "⚠"
                }

            # Risk analysis
            if extracted.key_risks:
                risk_count = len(extracted.key_risks)
                results["checks"]["risks"] = {
                    "count": risk_count,
                    "status": "✓" if risk_count >= 3 else "⚠"
                }

            # Confidence scores
            avg_confidence = self._calculate_avg_confidence(extracted)
            results["checks"]["avg_confidence"] = {
                "score": round(avg_confidence, 2),
                "status": "✓" if avg_confidence >= 0.7 else "⚠"
            }

            self._print_results(results)
            return results

        except ValidationError as e:
            print(f"✗ Validation FAILED: {e}")
            return {"valid": False, "error": str(e)}
        except Exception as e:
            print(f"✗ Error: {e}")
            return {"valid": False, "error": str(e)}

    def compare_outputs(self, golden_path: Path, new_path: Path) -> Dict:
        """Compare new extraction against golden dataset"""
        print(f"\n{'='*60}")
        print(f"Comparing: {new_path.name}")
        print(f"Against:   {golden_path.name}")
        print(f"{'='*60}")

        golden_data = json.loads(golden_path.read_text())["data"]
        new_data = json.loads(new_path.read_text())["data"]

        differences = {
            "file": new_path.name,
            "timestamp": datetime.now().isoformat(),
            "changes": []
        }

        # Compare key fields
        comparisons = [
            ("company_info.company_name", "Company Name"),
            ("financials.revenue_by_year", "Revenue Data"),
            ("financials.currency", "Currency"),
            ("key_risks", "Risk Count"),
            ("management_team", "Management Team Size"),
            ("transaction_details.asking_price", "Asking Price"),
        ]

        for path, label in comparisons:
            golden_val = self._get_nested(golden_data, path)
            new_val = self._get_nested(new_data, path)

            if golden_val != new_val:
                differences["changes"].append({
                    "field": label,
                    "golden": golden_val,
                    "new": new_val,
                    "severity": self._assess_severity(path, golden_val, new_val)
                })

        self._print_comparison(differences)
        return differences

    def validate_all_golden_outputs(self) -> Dict:
        """Validate all files in golden_outputs directory"""
        print(f"\n{'='*60}")
        print("VALIDATING ALL GOLDEN OUTPUTS")
        print(f"{'='*60}")

        if not self.golden_dir.exists():
            print(f"✗ Golden outputs directory not found: {self.golden_dir}")
            print(f"  Run with --mode=generate to create it")
            return {"error": "No golden dataset"}

        results = []
        golden_files = list(self.golden_dir.glob("*.json"))

        if not golden_files:
            print(f"✗ No JSON files found in {self.golden_dir}")
            return {"error": "No golden files"}

        for golden_file in golden_files:
            result = self.validate_structure(golden_file)
            results.append(result)

        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        valid_count = sum(1 for r in results if r.get("valid"))
        print(f"✓ Valid: {valid_count}/{len(results)}")
        print(f"✗ Invalid: {len(results) - valid_count}/{len(results)}")

        return {"results": results, "summary": {"valid": valid_count, "total": len(results)}}

    def _calculate_avg_confidence(self, extracted: ExtractedData) -> float:
        """Calculate average confidence across sections"""
        confidences = []
        for field_name in ["company_info", "financials", "balance_sheet", "market", "customers"]:
            section = getattr(extracted, field_name, None)
            if section and hasattr(section, "confidence") and section.confidence:
                confidences.append(section.confidence)
        return sum(confidences) / len(confidences) if confidences else 0.0

    def _get_nested(self, data: Dict, path: str):
        """Get nested value from dict using dot notation"""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None

        # For list comparisons, return length
        if isinstance(value, list):
            return len(value)
        return value

    def _assess_severity(self, field_path: str, golden, new) -> str:
        """Assess severity of difference"""
        # Critical fields
        if "asking_price" in field_path or "revenue" in field_path:
            return "HIGH"
        # Important fields
        if "company_name" in field_path or "currency" in field_path:
            return "MEDIUM"
        # Nice to have
        return "LOW"

    def _print_results(self, results: Dict):
        """Pretty print validation results"""
        print(f"\nValidation Results:")
        for section, data in results.get("checks", {}).items():
            if isinstance(data, dict):
                status = data.get("status", "?")
                if "years" in data:
                    print(f"  {status} {section}: {data['years']} years")
                elif "count" in data:
                    print(f"  {status} {section}: {data['count']} items")
                elif "score" in data:
                    print(f"  {status} {section}: {data['score']}")
                else:
                    print(f"  {status} {section}")

    def _print_comparison(self, differences: Dict):
        """Pretty print comparison results"""
        changes = differences.get("changes", [])

        if not changes:
            print("✓ No significant differences found!")
            return

        print(f"\nFound {len(changes)} difference(s):")
        for change in changes:
            severity_icon = "🔴" if change["severity"] == "HIGH" else "🟡" if change["severity"] == "MEDIUM" else "🟢"
            print(f"\n{severity_icon} {change['field']} ({change['severity']})")
            print(f"   Golden: {change['golden']}")
            print(f"   New:    {change['new']}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test extraction quality")
    parser.add_argument("--mode", choices=["validate", "compare", "generate"],
                       default="validate", help="Test mode")
    parser.add_argument("--golden", help="Path to golden output file (for compare mode)")
    parser.add_argument("--new", help="Path to new output file (for compare mode)")

    args = parser.parse_args()

    tester = ExtractionTester()

    if args.mode == "validate":
        tester.validate_all_golden_outputs()

    elif args.mode == "compare":
        if not args.golden or not args.new:
            print("Error: --golden and --new required for compare mode")
            sys.exit(1)
        tester.compare_outputs(Path(args.golden), Path(args.new))

    elif args.mode == "generate":
        print("Generate mode:")
        print("1. Place sample CIM PDFs in tests/data/sample_cims/")
        print("2. Upload them via your API (costs money!)")
        print("3. Save responses to tests/data/golden_outputs/")
        print("4. Manually review for accuracy")
        print("\nThis mode requires manual steps and API costs.")


if __name__ == "__main__":
    main()
