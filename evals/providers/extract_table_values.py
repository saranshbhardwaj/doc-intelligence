"""Custom promptfoo provider: extract_table_values_rag stage.

Replays stored system_prompt + user_message from llm_io_logs through
messages.create (same API as production — tables use raw JSON, not structured output).

Vars expected (written by export_eval_dataset.py):
    system_prompt  – full system prompt (RAG context chunks embedded)
    user_message   – full user message (table schema + extraction request)
    prompt_version – informational only
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))


def call_api(prompt, options, context):
    import anthropic
    from app.config import settings

    vars_ = context.get("vars", {})
    system_prompt = vars_.get("system_prompt", "")
    user_message = vars_.get("user_message", "")

    if not system_prompt or not user_message:
        return {"error": "Missing system_prompt or user_message in test vars"}

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        # Streaming required by Anthropic API when max_tokens is large (>~21k)
        with client.messages.stream(
            model=settings.synthesis_llm_model,
            max_tokens=settings.synthesis_llm_max_tokens,
            temperature=0.0,
            system=[{"type": "text", "text": system_prompt}],
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            response = stream.get_final_message()
    except Exception as exc:
        return {"error": str(exc)}

    raw_text = response.content[0].text.strip()

    # Strip markdown fences (same as production)
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
        raw_text = re.sub(r"\n?```$", "", raw_text)

    try:
        raw_result = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse failed: {exc}\nRaw: {raw_text[:300]}"}

    # Normalise to the io_log output shape: {results: [...], total_tables: N}
    results = raw_result.get("results", [])
    output = {
        "results": results,
        "total_tables": len(results),
        "total_rows": sum(len(t.get("rows", [])) for t in results),
    }

    usage = response.usage
    inp = usage.input_tokens or 0
    out = usage.output_tokens or 0
    # Haiku pricing: $0.80/MTok input, $5.00/MTok output
    cost = (inp * 0.0000008) + (out * 0.000005)

    return {
        "output": json.dumps(output),
        "tokenUsage": {"total": inp + out, "prompt": inp, "completion": out},
        "cost": cost,
    }
