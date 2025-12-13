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
        # Skip null values entirely (LLM should omit, not nullify)
        if value is None:
            logger.debug(f"Normalizer: Omitting null field '{key}'")
            continue

        # Workflow-specific normalization: Investment Memo sections
        if key == "sections" and workflow_name == "Investment Memo":
            # If sections is a single string, or list of strings, convert to list of objects
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
                logger.warning("Normalizer: Converting sections from string array to object array")
                normalized_sections = []
                for title in value:
                    section_key = title.lower().replace(" ", "_").replace("&", "and").replace("/", "_")
                    normalized_sections.append({
                        "key": section_key,
                        "title": title,
                        # use a visible placeholder so schema 'content' exists and UI shows intent
                        "content": "[Content not generated]",
                        "citations": []
                    })
                normalized[key] = normalized_sections
                continue

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


def handle_llm_result(run_id: str, combined_context: str, llm_result: Dict[str, Any]):
    """
    Persist raw LLM response, do fast safety checks and extract citation info.

    Returns:
        {
            "raw_text": str,
            "parsed_candidate": Optional[dict],
            "used_citations": List[str],
            "invalid_citations": List[str],
            "usage_meta": dict,
            "json_ok": bool,
            "json_parsed": Optional[dict],
            "json_err": str|None
        }
    """
    raw_text = (llm_result.get("raw_text") or llm_result.get("raw") or json.dumps(llm_result))
    usage_meta = llm_result.get("usage", {})

    # Safety check: ensure raw_text is a string
    if not isinstance(raw_text, str):
        logger.error(f"raw_text is not a string: {type(raw_text)}, llm_result keys: {llm_result.keys() if isinstance(llm_result, dict) else 'not a dict'}")
        raw_text = str(raw_text) if raw_text is not None else "{}"

    # Persist raw immediately for auditing (implement persist_raw_llm_response to suit your storage)
    try:
        save_raw_llm_response(run_id, {"raw": raw_text, "usage": usage_meta}, "workflow_llm_response")
    except Exception as e:
        logger.exception("Failed to persist raw llm response", extra={"run_id": run_id, "error": str(e)})

    # Extract citations used by LLM
    used_citations = re.findall(r"\[D\d+:p\d+\]", raw_text)
    allowed_citations = set(re.findall(r"\[D\d+:p\d+\]", combined_context))
    invalid_citations = [c for c in used_citations if c not in allowed_citations]

    # Try to parse JSON robustly (top-level object), but do a lightweight parse only
    json_ok = False
    json_parsed = None
    json_err = None
    try:
        txt = raw_text.strip()
        # strip fenced blocks if present (common LLM output)
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt, re.IGNORECASE)
        if m:
            txt = m.group(1).strip()
        m2 = re.search(r"~~~(?:json)?\s*([\s\S]*?)\s*~~~", txt, re.IGNORECASE)
        if m2:
            txt = m2.group(1).strip()

        # Strip preamble text if LLM added explanatory text before JSON
        # Handles cases like "Based on the document, here's the result: {...}"
        if not txt.startswith('{') and not txt.startswith('['):
            json_start = min(
                (txt.find('{') if '{' in txt else len(txt)),
                (txt.find('[') if '[' in txt else len(txt))
            )
            if json_start < len(txt):
                logger.warning(f"LLM response had preamble text (first {json_start} chars), extracting JSON only", extra={"run_id": run_id})
                txt = txt[json_start:]

        maybe = json.loads(txt)
        if isinstance(maybe, dict) and maybe:
            json_ok = True
            json_parsed = maybe
    except json.JSONDecodeError as je:
        json_err = str(je)
        # fallback: extract first JSON object substring
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if match:
            try:
                maybe = json.loads(match.group(0))
                if isinstance(maybe, dict) and maybe:
                    json_ok = True
                    json_parsed = maybe
                    json_err = None
            except Exception:
                pass

    parsed_candidate = llm_result.get("data") if isinstance(llm_result.get("data"), dict) else None

    return {
        "raw_text": raw_text,
        "parsed_candidate": parsed_candidate,
        "used_citations": used_citations,
        "invalid_citations": invalid_citations,
        "usage_meta": usage_meta,
        "json_ok": json_ok,
        "json_parsed": json_parsed,
        "json_err": json_err,
    }


def _get_db_session():
    """Get database session."""
    return next(get_db())


def _llm():
    """Initialize LLM client with cheap model for section summarization (map phase)."""
    return LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.cheap_llm_model,  # Haiku for cost-effective summarization
        max_tokens=settings.cheap_llm_max_tokens,
        max_input_chars=settings.llm_max_input_chars,
        timeout_seconds=settings.cheap_llm_timeout_seconds,
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
