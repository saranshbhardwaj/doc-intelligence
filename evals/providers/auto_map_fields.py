"""Custom promptfoo provider: auto_map_fields stage.

Calls the real TemplateFillLLMService.auto_map_fields() so evals test the
actual batch-sheet mapping logic, not just stored prompt text.

Expected vars in the test case:
    pdf_fields_json   – JSON string of the Azure DI fields list
    excel_schema_json – JSON string of the full Excel template schema
    prompt_version    – (optional) "v1", "v2", … — defaults to "v1"

Note: auto_map_fields makes multiple LLM calls (one per 4-sheet batch) and
aggregates results. Token usage reported here is the total across all batches.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))
os.environ.setdefault("ANTHROPIC_API_KEY", "")


def call_api(prompt, options, context):
    from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService

    vars_ = context.get("vars", {})
    pdf_fields = json.loads(vars_.get("pdf_fields_json", "[]"))
    excel_schema = json.loads(vars_.get("excel_schema_json", "{}"))
    prompt_version = vars_.get("prompt_version", "v1")

    if not pdf_fields or not excel_schema:
        return {"error": "Missing pdf_fields_json or excel_schema_json in test vars"}

    svc = TemplateFillLLMService(prompt_version=prompt_version)

    try:
        result = asyncio.run(svc.auto_map_fields(pdf_fields, excel_schema))
    except Exception as exc:
        return {"error": str(exc)}

    # Sum token usage across all batch io_log entries
    total_inp = sum(e.get("input_tokens", 0) or 0 for e in svc.io_log)
    total_out = sum(e.get("output_tokens", 0) or 0 for e in svc.io_log)

    return {
        "output": json.dumps(result),
        "tokenUsage": {"total": total_inp + total_out, "prompt": total_inp, "completion": total_out},
    }
