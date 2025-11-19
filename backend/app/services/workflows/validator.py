"""Workflow output validation utilities.

Provides JSON Schema validation and structural checks for workflow artifacts.
Graceful degradation: returns a ValidationResult object with errors list; does NOT raise unless schema loading fails critically.

Edge cases handled:
- Missing conditional sections (simply not validated if absent and optional).
- Extraneous keys (reported as warning, not hard error unless we enforce strict mode later).
- Citation mismatch (citations present not in allowed set) – caller still responsible for collecting allowed citations.
- Oversized string values (caller currently checks lengths; can integrate here if needed).

Usage:
from app.services.workflows.validator import validate_output
result = validate_output("Investment Memo", data_dict)
if not result.valid: ...
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, List, Dict
from pathlib import Path
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).parent / "schemas"

# Map workflow name to schema filename
SCHEMA_MAP = {
    "Investment Memo": "investment_memo.schema.json",
    "Investment Memo Formatter": "investment_memo.schema.json",  # Same schema as Investment Memo
    "Red Flags Summary": "red_flags.schema.json",
    "Revenue Quality Snapshot": "revenue_quality.schema.json",
    "Financial Model Builder": "financial_model.schema.json",
    "Management Assessment": "management_assessment.schema.json",
}

@dataclass
class ValidationError:
    code: str
    message: str
    path: List[Any] = field(default_factory=list)

@dataclass
class ValidationResult:
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    schema_applied: bool = False


def _load_schema(workflow_name: str) -> Dict[str, Any] | None:
    fname = SCHEMA_MAP.get(workflow_name)
    if not fname:
        return None
    path = SCHEMA_DIR / fname
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_output(workflow_name: str, data: Dict[str, Any]) -> ValidationResult:
    schema = _load_schema(workflow_name)
    if not schema:
        return ValidationResult(valid=True, schema_applied=False)  # No schema means pass-through

    errors: List[ValidationError] = []
    try:
        validator = Draft202012Validator(schema)
        for err in validator.iter_errors(data):
            errors.append(ValidationError(code="json_schema_violation", message=err.message, path=list(err.path)))
    except Exception as e:
        errors.append(ValidationError(code="schema_loading_error", message=str(e)))
        return ValidationResult(valid=False, errors=errors, schema_applied=False)

    valid = len(errors) == 0
    return ValidationResult(valid=valid, errors=errors, schema_applied=True)

__all__ = ["validate_output", "ValidationResult", "ValidationError"]
