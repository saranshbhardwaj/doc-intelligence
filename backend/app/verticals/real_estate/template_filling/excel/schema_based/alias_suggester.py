"""Alias Suggester Tool for Schema-Based Template Filling.

Analyzes past fill runs to suggest missing PDF aliases for schema fields.
This helps improve schema coverage over time by learning from real documents.

Usage:
    python -m app.verticals.real_estate.template_filling.excel.schema_based.alias_suggester \
        --schema re_investment_v1 \
        --min-samples 3
"""

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

from app.utils.logging import logger


@dataclass
class AliasSuggestion:
    """A suggested alias for a schema field."""
    alias: str
    seen_count: int
    similarity_score: float
    example_values: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alias": self.alias,
            "seen_count": self.seen_count,
            "similarity_score": round(self.similarity_score, 2),
            "example_values": self.example_values[:3],  # First 3 examples
        }


@dataclass
class FieldSuggestions:
    """Suggestions for a single schema field."""
    field_id: str
    current_aliases: List[str]
    suggested_additions: List[AliasSuggestion]
    unmapped_pdf_fields: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_id": self.field_id,
            "current_aliases": self.current_aliases,
            "suggested_additions": [s.to_dict() for s in self.suggested_additions],
            "unmapped_pdf_fields": self.unmapped_pdf_fields,
        }


class AliasSuggester:
    """Suggests missing PDF aliases based on past fill run data."""

    def __init__(self, similarity_threshold: float = 0.6):
        """
        Initialize the suggester.

        Args:
            similarity_threshold: Minimum similarity score for suggestions (0.0-1.0)
        """
        self.similarity_threshold = similarity_threshold

    def calculate_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate similarity between two strings.

        Uses SequenceMatcher for fuzzy matching.
        """
        # Normalize strings
        s1_norm = s1.lower().strip()
        s2_norm = s2.lower().strip()

        # Exact match
        if s1_norm == s2_norm:
            return 1.0

        # Fuzzy match
        return SequenceMatcher(None, s1_norm, s2_norm).ratio()

    def find_similar_aliases(
        self,
        pdf_field_name: str,
        current_aliases: List[str],
        threshold: Optional[float] = None
    ) -> Optional[Tuple[str, float]]:
        """
        Check if a PDF field name is similar to any current alias.

        Args:
            pdf_field_name: The PDF field name to check
            current_aliases: List of current aliases in schema
            threshold: Override similarity threshold

        Returns:
            Tuple of (best_matching_alias, similarity_score) or None
        """
        threshold = threshold or self.similarity_threshold
        best_match = None
        best_score = 0.0

        for alias in current_aliases:
            score = self.calculate_similarity(pdf_field_name, alias)
            if score > best_score:
                best_score = score
                best_match = alias

        if best_score >= threshold:
            return (best_match, best_score)
        return None

    def suggest_aliases(
        self,
        schema_fields: List[Dict[str, Any]],
        pdf_field_history: List[Dict[str, Any]],
        min_samples: int = 3
    ) -> List[FieldSuggestions]:
        """
        Analyze PDF field history and suggest missing aliases.

        Args:
            schema_fields: List of schema field definitions with pdf_aliases
            pdf_field_history: List of PDF fields from past fill runs
                [{"name": "...", "extracted_value": "...", "fill_run_id": "..."}, ...]
            min_samples: Minimum times a field must appear to suggest

        Returns:
            List of FieldSuggestions for each schema field
        """
        suggestions = []

        # Build alias index for all schema fields
        alias_to_field = {}
        for field_def in schema_fields:
            field_id = field_def.get("id")
            for alias in field_def.get("pdf_aliases", []):
                alias_to_field[alias.lower()] = field_id

        # Count PDF field occurrences
        pdf_field_counts: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "values": [], "fill_runs": set()}
        )

        for pdf_field in pdf_field_history:
            name = pdf_field.get("name", "").strip()
            if not name:
                continue

            name_key = name.lower()
            pdf_field_counts[name_key]["count"] += 1
            pdf_field_counts[name_key]["original_name"] = name
            if pdf_field.get("extracted_value"):
                pdf_field_counts[name_key]["values"].append(pdf_field["extracted_value"])
            if pdf_field.get("fill_run_id"):
                pdf_field_counts[name_key]["fill_runs"].add(pdf_field["fill_run_id"])

        # For each schema field, find potential new aliases
        for field_def in schema_fields:
            field_id = field_def.get("id")
            current_aliases = field_def.get("pdf_aliases", [])

            field_suggestions = FieldSuggestions(
                field_id=field_id,
                current_aliases=current_aliases,
                suggested_additions=[],
                unmapped_pdf_fields=[]
            )

            # Check each PDF field for similarity
            for name_key, data in pdf_field_counts.items():
                # Skip if seen less than min_samples times
                if data["count"] < min_samples:
                    continue

                original_name = data.get("original_name", name_key)

                # Skip if already an exact alias match
                if any(alias.lower() == name_key for alias in current_aliases):
                    continue

                # Check similarity to current aliases
                match = self.find_similar_aliases(original_name, current_aliases)

                if match:
                    # Similar to existing alias - suggest as addition
                    similarity = match[1]
                    suggestion = AliasSuggestion(
                        alias=original_name,
                        seen_count=data["count"],
                        similarity_score=similarity,
                        example_values=data["values"][:3]
                    )
                    field_suggestions.suggested_additions.append(suggestion)
                else:
                    # Not similar - might need manual review
                    # Check if it matches a DIFFERENT schema field
                    if name_key not in alias_to_field:
                        # Truly unmapped - suggest it for manual categorization
                        field_suggestions.unmapped_pdf_fields.append({
                            "name": original_name,
                            "count": data["count"],
                            "example_values": data["values"][:3]
                        })

            # Sort suggestions by count (most common first)
            field_suggestions.suggested_additions.sort(
                key=lambda s: (-s.seen_count, -s.similarity_score)
            )

            suggestions.append(field_suggestions)

        return suggestions

    def generate_yaml_patch(self, suggestions: List[FieldSuggestions]) -> str:
        """
        Generate YAML patch to add suggested aliases.

        Args:
            suggestions: List of field suggestions

        Returns:
            YAML snippet to add to schema
        """
        lines = ["# Suggested alias additions (copy to schema YAML)", ""]

        for fs in suggestions:
            if not fs.suggested_additions:
                continue

            lines.append(f"# Field: {fs.field_id}")
            lines.append(f"# Current aliases: {fs.current_aliases}")
            lines.append("# Add these aliases:")
            for suggestion in fs.suggested_additions:
                lines.append(f'#   - "{suggestion.alias}"  # seen {suggestion.seen_count}x, {int(suggestion.similarity_score * 100)}% similar')
            lines.append("")

        return "\n".join(lines)


def suggest_aliases_from_database(
    schema_id: str,
    min_samples: int = 3,
    similarity_threshold: float = 0.6
) -> Dict[str, Any]:
    """
    Query database for past fill runs and suggest aliases.

    Args:
        schema_id: The schema ID to analyze
        min_samples: Minimum occurrences to suggest
        similarity_threshold: Minimum similarity score

    Returns:
        Dictionary with suggestions and stats
    """
    from app.database import SessionLocal
    from app.repositories.template_repository import TemplateRepository
    from app.verticals.real_estate.template_filling.excel.schema_based.schema_loader import SchemaLoader

    db = SessionLocal()
    repo = TemplateRepository(db)

    try:
        # Load schema
        schema_loader = SchemaLoader()
        schema = schema_loader.load_schema(schema_id)

        if not schema:
            return {
                "error": f"Schema '{schema_id}' not found",
                "available_schemas": schema_loader.list_available_schemas()
            }

        # Get all fill runs (to extract PDF field history)
        # This would need a custom query - simplified for now
        fill_runs = repo.list_fill_runs(limit=1000)

        # Extract PDF fields from all fill runs
        pdf_field_history = []
        for fill_run in fill_runs:
            if fill_run.field_mapping and "pdf_fields" in fill_run.field_mapping:
                for pdf_field in fill_run.field_mapping["pdf_fields"]:
                    pdf_field_history.append({
                        "name": pdf_field.get("name"),
                        "extracted_value": pdf_field.get("extracted_value"),
                        "fill_run_id": fill_run.id
                    })

        # Run suggester
        suggester = AliasSuggester(similarity_threshold=similarity_threshold)
        schema_fields = [f.__dict__ for f in schema.fields]

        suggestions = suggester.suggest_aliases(
            schema_fields=schema_fields,
            pdf_field_history=pdf_field_history,
            min_samples=min_samples
        )

        # Generate stats
        total_suggestions = sum(len(fs.suggested_additions) for fs in suggestions)
        total_unmapped = sum(len(fs.unmapped_pdf_fields) for fs in suggestions)

        return {
            "schema_id": schema_id,
            "fill_runs_analyzed": len(fill_runs),
            "pdf_fields_analyzed": len(pdf_field_history),
            "total_suggestions": total_suggestions,
            "total_unmapped": total_unmapped,
            "suggestions": [fs.to_dict() for fs in suggestions if fs.suggested_additions or fs.unmapped_pdf_fields],
            "yaml_patch": suggester.generate_yaml_patch(suggestions)
        }

    finally:
        db.close()


def main():
    """CLI entry point for alias suggester."""
    parser = argparse.ArgumentParser(
        description="Suggest missing PDF aliases for schema fields"
    )
    parser.add_argument(
        "--schema", "-s",
        required=True,
        help="Schema ID to analyze (e.g., re_investment_v1)"
    )
    parser.add_argument(
        "--min-samples", "-m",
        type=int,
        default=3,
        help="Minimum occurrences to suggest (default: 3)"
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=0.6,
        help="Similarity threshold 0.0-1.0 (default: 0.6)"
    )
    parser.add_argument(
        "--output", "-o",
        choices=["json", "yaml", "summary"],
        default="summary",
        help="Output format (default: summary)"
    )

    args = parser.parse_args()

    result = suggest_aliases_from_database(
        schema_id=args.schema,
        min_samples=args.min_samples,
        similarity_threshold=args.threshold
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        if "available_schemas" in result:
            print(f"Available schemas: {result['available_schemas']}")
        return

    if args.output == "json":
        import json
        print(json.dumps(result, indent=2))

    elif args.output == "yaml":
        print(result["yaml_patch"])

    else:  # summary
        print(f"\n{'='*60}")
        print(f"Alias Suggestions for: {result['schema_id']}")
        print(f"{'='*60}")
        print(f"Fill runs analyzed: {result['fill_runs_analyzed']}")
        print(f"PDF fields analyzed: {result['pdf_fields_analyzed']}")
        print(f"Total suggestions: {result['total_suggestions']}")
        print(f"Unmapped fields: {result['total_unmapped']}")
        print()

        for fs in result["suggestions"]:
            if fs["suggested_additions"]:
                print(f"\n📌 Field: {fs['field_id']}")
                print(f"   Current: {fs['current_aliases']}")
                print("   Suggested additions:")
                for s in fs["suggested_additions"]:
                    print(f"     - \"{s['alias']}\" (seen {s['seen_count']}x, {int(s['similarity_score']*100)}% similar)")

            if fs["unmapped_pdf_fields"]:
                print(f"\n⚠️  Unmapped PDF fields (might belong to {fs['field_id']} or other fields):")
                for uf in fs["unmapped_pdf_fields"]:
                    print(f"     - \"{uf['name']}\" (seen {uf['count']}x)")

        print()
        print("="*60)
        print("To add suggestions, copy the YAML patch below to your schema:")
        print("="*60)
        print(result["yaml_patch"])


if __name__ == "__main__":
    main()
