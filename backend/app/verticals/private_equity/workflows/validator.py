"""Workflow output validation utilities.

Provides JSON Schema validation and structural checks for workflow artifacts.
Graceful degradation: returns a ValidationResult object with errors list; does NOT raise unless schema loading fails critically.

Edge cases handled:
- Missing conditional sections (simply not validated if absent and optional).
- Extraneous keys (reported as warning, not hard error unless we enforce strict mode later).
- Citation mismatch (citations present not in allowed set) – caller still responsible for collecting allowed citations.
- Oversized string values (caller currently checks lengths; can integrate here if needed).

Usage:
from app.verticals.private_equity.workflows.validator import validate_output
result = validate_output("Investment Memo", data_dict)
if not result.valid: ...
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, List, Dict
from pathlib import Path
from jsonschema import Draft202012Validator
from app.utils.logging import logger

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
        logger.warning(f"No schema mapping found for workflow '{workflow_name}'")
        return None
    path = SCHEMA_DIR / fname
    if not path.exists():
        logger.error(f"Schema file not found: {path}")
        return None
    logger.info(f"Loading schema from: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_output(workflow_name: str, data: Dict[str, Any]) -> ValidationResult:
    schema = _load_schema(workflow_name)
    if not schema:
        logger.info(f"No schema found for '{workflow_name}', skipping validation")
        return ValidationResult(valid=True, schema_applied=False)  # No schema means pass-through

    # Log data structure summary
    logger.info(f"Validating '{workflow_name}' output against schema")
    logger.info(f"Data structure: top-level keys = {list(data.keys())}")
    if "sections" in data:
        logger.info(f"  sections: {len(data.get('sections', []))} items")
    if "risks" in data:
        logger.info(f"  risks: {len(data.get('risks', []))} items")
    if "opportunities" in data:
        logger.info(f"  opportunities: {len(data.get('opportunities', []))} items")
    if "references" in data:
        logger.info(f"  references: {len(data.get('references', []))} items")
    if "meta" in data:
        logger.info(f"  meta: {data.get('meta')}")

    errors: List[ValidationError] = []
    try:
        validator = Draft202012Validator(schema)
        for err in validator.iter_errors(data):
            error_obj = ValidationError(code="json_schema_violation", message=err.message, path=list(err.path))
            errors.append(error_obj)

            # Log each error with detailed context
            path_str = " -> ".join(str(p) for p in err.path) if err.path else "root"
            validator_val = str(err.validator_value)[:200] if hasattr(err, 'validator_value') else "N/A"
            instance_val = str(err.instance)[:200] if hasattr(err, 'instance') else "N/A"

            logger.error(
                f"Schema validation error #{len(errors)}: "
                f"path='{path_str}', "
                f"message='{err.message}', "
                f"validator='{err.validator}', "
                f"expected={validator_val}, "
                f"actual={instance_val}"
            )
    except Exception as e:
        logger.error(f"Schema validation exception: {e}", exc_info=True)
        errors.append(ValidationError(code="schema_loading_error", message=str(e)))
        return ValidationResult(valid=False, errors=errors, schema_applied=False)

    valid = len(errors) == 0
    if valid:
        logger.info(f"✓ Schema validation passed for '{workflow_name}'")
    else:
        logger.error(f"✗ Schema validation failed for '{workflow_name}' with {len(errors)} error(s)")

    return ValidationResult(valid=valid, errors=errors, schema_applied=True)


__all__ = ["validate_output", "ValidationResult", "ValidationError"]
