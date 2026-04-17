# Schema-Based Excel Template Mapping

## Overview

This module provides **deterministic, rule-based mapping** for known Excel templates using YAML schema definitions. No LLM required for schema-defined fields.

## Architecture

```
schema_based/
├── __init__.py                    # Module exports
├── schema_loader.py               # Load & validate YAML schemas
├── template_identifier.py         # Fingerprint matching
├── schema_mapper.py               # Direct alias-based mapping
├── schemas/
│   └── re_investment_v1.yaml      # Your template definition
└── README.md                      # This file
```

## Usage

### 1. Define Your Schema

Edit `schemas/re_investment_v1.yaml`:

```yaml
schema_id: "re_investment_v1"
version: "1.0"
name: "RE Investment Model"

# Fingerprint cells - identify template (3-5 unique cells)
fingerprint:
  - sheet: "DASHBOARD"
    cell: "B6"
    expected_value: "Unit Count"

# Critical fields (50-100 most important)
fields:
  - id: "unit_count"
    sheet: "DASHBOARD"
    label_cell: "B6"
    value_cell: "C6"
    data_type: "number"
    pdf_aliases:
      - "Units"
      - "Unit Count"
      - "Total Units"
```

### 2. Use in Fill Workflow

```python
from openpyxl import load_workbook
from .schema_based import SchemaLoader, TemplateIdentifier, SchemaMapper

# Initialize
schema_loader = SchemaLoader()
identifier = TemplateIdentifier(schema_loader)

# Load template
workbook = load_workbook("template.xlsx")

# Identify template
schema_id = identifier.identify(workbook)

if schema_id:
    # Template matched - use schema mapping
    schema = schema_loader.load_schema(schema_id)
    mapper = SchemaMapper(schema)

    # Map fields (deterministic, no LLM)
    schema_mappings = mapper.map_fields(pdf_fields)

    print(f"Schema mapping: {len(schema_mappings)} fields mapped")
else:
    # Unknown template - fall back to generic analyzer
    print("No schema match - using generic analyzer")
```

### 3. Hybrid Mode (Schema + Generic)

```python
# Step 1: Try schema mapping
schema_mappings = []
if schema_id:
    schema = schema_loader.load_schema(schema_id)
    mapper = SchemaMapper(schema)
    schema_mappings = mapper.map_fields(pdf_fields)

# Step 2: Generic + LLM for unmapped cells
schema_mapped_cells = {f"{m['excel_sheet']}!{m['excel_cell']}" for m in schema_mappings}

# Run generic analyzer (existing code)
generic_schema = template_analyzer.analyze(workbook)

# Filter out schema-mapped cells
filtered_schema = filter_generic_schema(generic_schema, schema_mapped_cells)

# Run LLM mapping on remaining cells
generic_mappings = await llm_service.map_fields(pdf_fields, filtered_schema)

# Merge (schema takes priority)
all_mappings = schema_mappings + generic_mappings
```

## Time Complexity

- **Index build**: O(F × A) where F = fields, A = aliases per field (done once at schema load)
- **Per PDF field lookup**: O(1) direct match, O(A_total) partial match (only when direct fails)
- **Total mapping**: O(P) where P = PDF fields (with direct matches), O(P × A_total) worst case

In practice: ~100 PDF fields × 50 schema fields × 5 aliases = ~25,000 operations max (sub-millisecond on modern hardware).

## Benefits

| Feature | Generic Analyzer | Schema-Based |
|---------|-----------------|--------------|
| Accuracy | 50-70% | 100% for defined fields |
| Speed | Slower (LLM calls) | Instant (dict lookup) |
| Consistency | Varies by run | Always same |
| Maintenance | None | Update YAML when template changes |
| User control | None | Full visibility into mappings |

## Configuration Options

When calling the fill workflow, pass config flags:

```python
config = {
    "schema_only": False,   # If True, ONLY use schema (skip generic)
    "skip_schema": False,   # If True, skip schema (use generic only)
}
```

## Adding New Templates

1. Create `schemas/my_template_v1.yaml`
2. Define fingerprint cells (3-5 unique)
3. Define critical fields (50-100)
4. Test with: `schema_loader.load_schema("my_template_v1")`
5. Schema will automatically be checked during identification

## Schema Versioning

When template layout changes:
1. Create `my_template_v2.yaml`
2. Update fingerprint if needed
3. Old v1 schema remains for backward compatibility
4. System will match based on fingerprint

## Debugging

```python
# List available schemas
schemas = schema_loader.list_available_schemas()
print(f"Available: {schemas}")

# Force reload (bypass cache)
schema = schema_loader.reload_schema("re_investment_v1")

# Check unmapped fields
unmapped = mapper.get_unmapped_schema_fields(mappings)
print(f"Schema fields without PDF data: {unmapped}")
```
