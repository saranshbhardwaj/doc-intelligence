"""Helper functions for workflow execution.

Utility functions for:
- LLM output normalization
- Template default extraction
- LLM result handling
- Database and LLM client initialization
"""
from typing import Dict, Any, List
import json
import re

from app.database import get_db
from app.services.llm_client import LLMClient
from app.db_models_workflows import Workflow
from app.utils.logging import logger
from app.config import settings
from app.utils.file_utils import save_raw_llm_response


def normalize_llm_output(data: Dict[str, Any], workflow_name: str) -> Dict[str, Any]:
    """Normalize common LLM output issues before schema validation.

    - Omits nulls
    - Converts string arrays to object arrays for known structures (e.g., sections)
    - Keeps placeholders so schema validation can run predictably
    """
    if not isinstance(data, dict):
        return data

    normalized = {}

    for key, value in data.items():

        # Recursively normalize nested objects
        if isinstance(value, dict):
            normalized_nested = normalize_llm_output(value, workflow_name)
            # include nested even if empty dict? only if keys exist after normalization
            if normalized_nested:
                normalized[key] = normalized_nested
            else:
                # keep empty object for known keys that schema expects an object (optionally)
                normalized[key] = {}
            continue

        # Normalize arrays
        if isinstance(value, list):
            normalized_list = []
            for item in value:
                if isinstance(item, dict):
                    # Recursively normalize objects in arrays
                    norm_item = normalize_llm_output(item, workflow_name)
                    # keep object (even if small), do not drop completely to avoid removing required items
                    normalized_list.append(norm_item)
                elif item is not None:  # Skip null items but keep primitives
                    normalized_list.append(item)

            # Always include lists even if empty (schema validation will catch minItems etc.)
            normalized[key] = normalized_list
            continue

        # Keep primitives as-is (string, number, bool)
        normalized[key] = value

    return normalized


def get_template_safe_defaults(workflow: Workflow) -> dict:
    """Extract default values from workflow's variable schema.

    Returns a dict of variable_name -> default_value for all variables
    that have defaults defined in the schema. This ensures template rendering
    never fails due to missing variables.

    Args:
        workflow: Workflow instance with variables_schema

    Returns:
        Dict of variable defaults, always including 'custom_objective'
    """
    safe_defaults = {
        "custom_objective": "",  # Always needed for dual-prompt architecture
    }

    if not workflow.variables_schema:
        return safe_defaults

    try:
        # variables_schema might be a string (JSON) or already parsed dict
        schema = workflow.variables_schema
        if isinstance(schema, str):
            schema = json.loads(schema)
        elif not isinstance(schema, dict):
            logger.warning(
                "Unexpected schema type",
                extra={
                    "workflow_id": workflow.id,
                    "workflow_name": workflow.name,
                    "schema_type": type(schema).__name__
                }
            )
            return safe_defaults

        # Ensure "variables" key exists
        if "variables" not in schema:
            logger.warning(
                "Schema missing 'variables' key",
                extra={
                    "workflow_id": workflow.id,
                    "workflow_name": workflow.name,
                    "schema_keys": list(schema.keys())
                }
            )
            return safe_defaults

        variables_list = schema.get("variables", [])
        if not isinstance(variables_list, list):
            logger.warning(
                "Schema 'variables' is not a list",
                extra={
                    "workflow_id": workflow.id,
                    "workflow_name": workflow.name,
                    "variables_type": type(variables_list).__name__
                }
            )
            return safe_defaults

        for var_def in variables_list:
            if not isinstance(var_def, dict):
                continue

            var_name = var_def.get("name")
            if not var_name:
                continue

            # Use explicit default if provided
            if "default" in var_def:
                safe_defaults[var_name] = var_def["default"]
            # Otherwise infer sensible default by type
            elif var_def.get("type") == "boolean":
                safe_defaults[var_name] = False
            elif var_def.get("type") == "integer":
                safe_defaults[var_name] = var_def.get("min", 0)
            elif var_def.get("type") == "number":
                safe_defaults[var_name] = var_def.get("min", 0.0)
            elif var_def.get("type") == "string":
                safe_defaults[var_name] = ""
            elif var_def.get("type") == "enum":
                choices = var_def.get("choices", [])
                safe_defaults[var_name] = choices[0] if choices else ""

    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse workflow schema JSON",
            extra={
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "error": str(e),
                "schema_preview": str(workflow.variables_schema)[:200] if workflow.variables_schema else None
            }
        )
    except Exception as e:
        logger.warning(
            "Failed to extract defaults from workflow schema",
            extra={
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "error": str(e),
                "error_type": type(e).__name__,
                "schema_type": type(workflow.variables_schema).__name__
            }
        )

    return safe_defaults


# def handle_llm_result(run_id: str, combined_context: str, llm_result: Dict[str, Any]):
#     """
#     Persist raw LLM response, do fast safety checks and extract citation info.

#     Returns:
#         {
#             "raw_text": str,
#             "parsed_candidate": Optional[dict],
#             "used_citations": List[str],
#             "invalid_citations": List[str],
#             "usage_meta": dict,
#             "json_ok": bool,
#             "json_parsed": Optional[dict],
#             "json_err": str|None
#         }
#     """
#     raw_text = (llm_result.get("raw_text") or llm_result.get("raw") or json.dumps(llm_result))
#     usage_meta = llm_result.get("usage", {})

#     # Safety check: ensure raw_text is a string
#     if not isinstance(raw_text, str):
#         logger.error(f"raw_text is not a string: {type(raw_text)}, llm_result keys: {llm_result.keys() if isinstance(llm_result, dict) else 'not a dict'}")
#         raw_text = str(raw_text) if raw_text is not None else "{}"

#     # Persist raw immediately for auditing (implement persist_raw_llm_response to suit your storage)
#     try:
#         save_raw_llm_response(run_id, {"raw": raw_text, "usage": usage_meta}, "workflow_llm_response")
#     except Exception as e:
#         logger.exception("Failed to persist raw llm response", extra={"run_id": run_id, "error": str(e)})

#     # Extract citations used by LLM
#     used_citations = re.findall(r"\[D\d+:p\d+\]", raw_text)
#     allowed_citations = set(re.findall(r"\[D\d+:p\d+\]", combined_context))
#     invalid_citations = [c for c in used_citations if c not in allowed_citations]

#     # Try to parse JSON robustly (top-level object), but do a lightweight parse only
#     json_ok = False
#     json_parsed = None
#     json_err = None
#     try:
#         txt = raw_text.strip()
#         # strip fenced blocks if present (common LLM output)
#         m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt, re.IGNORECASE)
#         if m:
#             txt = m.group(1).strip()
#         m2 = re.search(r"~~~(?:json)?\s*([\s\S]*?)\s*~~~", txt, re.IGNORECASE)
#         if m2:
#             txt = m2.group(1).strip()

#         # Strip preamble text if LLM added explanatory text before JSON
#         # Handles cases like "Based on the document, here's the result: {...}"
#         if not txt.startswith('{') and not txt.startswith('['):
#             json_start = min(
#                 (txt.find('{') if '{' in txt else len(txt)),
#                 (txt.find('[') if '[' in txt else len(txt))
#             )
#             if json_start < len(txt):
#                 logger.warning(f"LLM response had preamble text (first {json_start} chars), extracting JSON only", extra={"run_id": run_id})
#                 txt = txt[json_start:]

#         maybe = json.loads(txt)
#         if isinstance(maybe, dict) and maybe:
#             json_ok = True
#             json_parsed = maybe
#     except json.JSONDecodeError as je:
#         json_err = str(je)
#         # fallback: extract first JSON object substring
#         match = re.search(r"\{[\s\S]*\}", raw_text)
#         if match:
#             try:
#                 maybe = json.loads(match.group(0))
#                 if isinstance(maybe, dict) and maybe:
#                     json_ok = True
#                     json_parsed = maybe
#                     json_err = None
#             except Exception:
#                 pass

#     parsed_candidate = llm_result.get("data") if isinstance(llm_result.get("data"), dict) else None

#     return {
#         "raw_text": raw_text,
#         "parsed_candidate": parsed_candidate,
#         "used_citations": used_citations,
#         "invalid_citations": invalid_citations,
#         "usage_meta": usage_meta,
#         "json_ok": json_ok,
#         "json_parsed": json_parsed,
#         "json_err": json_err,
#     }

def handle_llm_result(run_id: str, combined_context: str, llm_result: Dict[str, Any]):
    """
    Post-process SDK-parsed LLM result.
    
    Since we use client.beta.messages.parse() with output_format=PydanticModel,
    JSON parsing and schema validation are already done by the SDK.
    This function handles:
    - Citation extraction and validation
    - Raw response persistence for auditing
    - Passing through the SDK-parsed data
    """
    
    raw_text = llm_result.get("raw_text", "{}")
    usage_meta = llm_result.get("usage", {})
    
    # Safety: ensure raw_text is string
    if not isinstance(raw_text, str):
        raw_text = str(raw_text) if raw_text else "{}"
    
    # Persist raw for auditing
    try:
        save_raw_llm_response(run_id, {"raw": raw_text, "usage": usage_meta}, "workflow_llm_response")
    except Exception as e:
        logger.exception("Failed to persist raw llm response", extra={"run_id": run_id})
    
    # Extract and validate citations
    used_citations = re.findall(r"\[D\d+:p\d+\]", raw_text)
    allowed_citations = set(re.findall(r"\[D\d+:p\d+\]", combined_context))
    invalid_citations = [c for c in used_citations if c not in allowed_citations]
    
    # SDK already parsed and validated - just pass through
    parsed_candidate = llm_result.get("data")  # This is parsed_output.model_dump()
    
    if not parsed_candidate:
        logger.error("SDK did not return parsed data", extra={"run_id": run_id})
    
    return {
        "raw_text": raw_text,
        "parsed_candidate": parsed_candidate,
        "used_citations": used_citations,
        "invalid_citations": invalid_citations,
        "usage_meta": usage_meta,
        "json_ok": parsed_candidate is not None,
        "json_parsed": parsed_candidate,
        "json_err": None if parsed_candidate else "SDK parsing failed",
    }

def _get_db_session():
    """Get database session."""
    return next(get_db())


def _llm():
    """Initialize LLM client with cheap model for section summarization (map phase)."""
    return LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.synthesis_llm_model,  # Haiku for cost-effective summarization
        max_tokens=settings.synthesis_llm_max_tokens,
        max_input_chars=settings.llm_max_input_chars,
        timeout_seconds=settings.synthesis_llm_timeout_seconds,
    )


def _llm_expensive(max_tokens: int = None):
    """
    Initialize LLM client with expensive model for final synthesis (reduce phase).

    Args:
        max_tokens: Optional custom max_tokens (defaults to synthesis_llm_max_tokens)
    """
    # Use synthesis-specific model settings (configured for testing with Haiku 4.5)
    # This allows cost-effective testing while keeping Sonnet for extraction tasks
    synthesis_max_tokens = max_tokens or settings.synthesis_llm_max_tokens

    return LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.synthesis_llm_model,  # Haiku 4.5 for cost-effective synthesis
        max_tokens=synthesis_max_tokens,
        max_input_chars=settings.llm_max_input_chars,
        timeout_seconds=settings.synthesis_llm_timeout_seconds,
    )

def validate_investment_memo_constraints(memo: dict) -> dict:
    """
    Validates constraints SDK can't enforce.
    
    Critical for simplified Pydantic model where:
    - Literal types were replaced with str
    - float fields were replaced with str (FinancialYear.revenue)
    - Array size limits were removed
    """

    issues = []   # Warnings (don't block)
    errors = []   # Hard errors (block)

    sections = memo.get("sections", [])
    actual_keys = {s.get("key") for s in sections}

    # ─────────────────────────────────────
    # 1. Section count
    # ─────────────────────────────────────
    required_sections = {
        "executive_overview", "company_overview", "market_competition",
        "financial_performance", "track_record_value_creation",
        "risks", "opportunities", "management_culture", "esg_snapshot",
        "valuation_scenarios", "next_steps", "inconsistencies"
    }
    missing = required_sections - actual_keys

    if missing:
        errors.append({
            "code": "missing_sections",
            "message": f"Missing sections: {missing}",
        })

    # ─────────────────────────────────────
    # 2. Citation format [D1:p2]
    # ─────────────────────────────────────
    citation_pattern = re.compile(r'^\[D\d+:p\d+\]$')

    for ref in memo.get("references", []):
        if not citation_pattern.match(ref):
            issues.append({  # Warning, not error (normalization may have fixed)
                "code": "invalid_citation_format",
                "message": f"Bad citation in references: '{ref}'",
            })

    for section in sections:
        for c in section.get("citations", []):
            if not citation_pattern.match(c):
                issues.append({
                    "code": "invalid_citation_format",
                    "message": f"Bad citation in {section.get('key')}: '{c}'",
                })

    # ─────────────────────────────────────
    # 3. Confidence range (clamp)
    # ─────────────────────────────────────
    for section in sections:
        confidence = section.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, (int, float)):
                issues.append({
                    "code": "confidence_not_numeric",
                    "message": f"Confidence in '{section.get('key')}' is not numeric: {confidence}",
                })
                section["confidence"] = None  # Remove bad value
            elif not (0.0 <= confidence <= 1.0):
                issues.append({
                    "code": "confidence_out_of_range",
                    "message": f"Confidence {confidence} in '{section.get('key')}' clamped to 0-1",
                })
                section["confidence"] = max(0.0, min(1.0, confidence))

    # ─────────────────────────────────────
    # 4. Content word count
    # ─────────────────────────────────────
    for section in sections:
        word_count = len(section.get("content", "").split())
        if word_count > 200:
            issues.append({
                "code": "content_too_long",
                "message": f"'{section.get('key')}': {word_count} words (target 100-150)",
            })

    # ─────────────────────────────────────
    # 5. Currency consistency
    # ─────────────────────────────────────
    top_currency = memo.get("currency")
    for section in sections:
        financials = section.get("financials")
        if financials and financials.get("currency") != top_currency:
            errors.append({
                "code": "currency_mismatch",
                "message": f"financials.currency='{financials.get('currency')}' != top-level '{top_currency}'",
            })

    # ─────────────────────────────────────
    # 6. Enum validation (CRITICAL for simplified model)
    #    Original model had Literal types, now plain str
    # ─────────────────────────────────────
    valid_severities = {"High", "Medium", "Low"}
    for i, risk in enumerate(memo.get("risks", [])):
        if risk.get("severity") not in valid_severities:
            errors.append({
                "code": "invalid_severity",
                "message": f"risks[{i}].severity='{risk.get('severity')}' not in {valid_severities}",
            })

    valid_impacts = {"High", "Medium", "Low"}
    for i, opp in enumerate(memo.get("opportunities", [])):
        if opp.get("impact") not in valid_impacts:
            errors.append({
                "code": "invalid_impact",
                "message": f"opportunities[{i}].impact='{opp.get('impact')}' not in {valid_impacts}",
            })

    valid_esg_statuses = {"Positive", "Neutral", "Negative"}
    esg = memo.get("esg", {})
    for i, factor in enumerate(esg.get("factors", [])):
        if factor.get("status") not in valid_esg_statuses:
            errors.append({
                "code": "invalid_esg_status",
                "message": f"esg.factors[{i}].status='{factor.get('status')}' not in {valid_esg_statuses}",
            })

    # ─────────────────────────────────────
    # 7. FinancialYear.revenue is now str
    #    Validate it's a parseable number
    # ─────────────────────────────────────
    for section in sections:
        financials = section.get("financials")
        if not financials:
            continue
        for i, year_data in enumerate(financials.get("historical", [])):
            revenue = year_data.get("revenue", "")
            # Strip formatting and check if numeric
            cleaned = str(revenue).replace(",", "").replace("$", "").replace("%", "").replace(" ", "").strip()
            try:
                float(cleaned)
            except (ValueError, TypeError):
                issues.append({
                    "code": "unparseable_revenue",
                    "message": f"historical[{i}].revenue='{revenue}' not parseable as number",
                })

            # Also validate year is reasonable
            year = year_data.get("year")
            if not isinstance(year, int) or not (2000 <= year <= 2030):
                issues.append({
                    "code": "invalid_year",
                    "message": f"historical[{i}].year='{year}' not a valid year (2000-2030)",
                })

    # ─────────────────────────────────────
    # 8. meta.version
    # ─────────────────────────────────────
    meta = memo.get("meta", {})
    if meta.get("version") != 2:
        issues.append({
            "code": "invalid_meta_version",
            "message": f"meta.version={meta.get('version')}, expected 2",
        })
        memo["meta"]["version"] = 2  # Force correct value

    # ─────────────────────────────────────
    # 9. Array size limits
    # ─────────────────────────────────────
    for section in sections:
        if len(section.get("highlights", [])) > 5:
            issues.append({
                "code": "too_many_highlights",
                "message": f"'{section.get('key')}': {len(section['highlights'])} highlights (max 5)",
            })
        if len(section.get("key_metrics", [])) > 6:
            issues.append({
                "code": "too_many_key_metrics",
                "message": f"'{section.get('key')}': {len(section['key_metrics'])} key_metrics (max 6)",
            })

    # ─────────────────────────────────────
    # 10. next_steps structure
    #     Simplified model uses Dict[str, Any]
    #     Validate required fields exist
    # ─────────────────────────────────────
    for i, step in enumerate(memo.get("next_steps", [])):
        for required_field in ["priority", "action", "owner", "timeline_days"]:
            if required_field not in step:
                issues.append({
                    "code": "missing_next_step_field",
                    "message": f"next_steps[{i}] missing '{required_field}'",
                })

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "issues": issues,
    }