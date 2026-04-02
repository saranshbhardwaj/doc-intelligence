"""Custom promptfoo provider: extract_schema_fields stage.

Replays stored system_prompt + user_message from llm_io_logs through
messages.parse (same structured-output API as production).

Vars expected (written by export_eval_dataset.py):
    system_prompt  – full system prompt (Azure DI fields embedded)
    user_message   – full user message (unmapped fields list embedded)
    prompt_version – informational only
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))


def call_api(prompt, options, context):
    import anthropic
    from app.verticals.real_estate.template_filling.prompts.v1 import SchemaFieldExtractionResult
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
            output_format=SchemaFieldExtractionResult,
        ) as stream:
            message = stream.get_final_message()
    except Exception as exc:
        return {"error": str(exc)}

    # With streaming + output_format the SDK returns JSON as a text block
    parsed = None
    for block in message.content:
        block_type = getattr(block, "type", None)
        if block_type == "tool_use":
            try:
                parsed = SchemaFieldExtractionResult(**block.input)
            except Exception as exc:
                return {"error": f"Failed to parse tool_use block: {exc}"}
            break
        elif block_type == "text":
            try:
                raw = json.loads(block.text)
                parsed = SchemaFieldExtractionResult(**raw)
            except Exception as exc:
                return {"error": f"Failed to parse text block as JSON: {exc}. text={block.text[:300]}"}
            break

    if parsed is None:
        return {"error": f"No usable content block. stop_reason={message.stop_reason}"}

    output = {
        "results": [
            {
                "field_id": item.field_id,
                "value": item.value,
                "confidence": item.confidence,
                "citations": item.citations,
                "reasoning": item.reasoning,
            }
            for item in parsed.results
        ],
        "total_found": parsed.total_found,
        "total_not_found": parsed.total_not_found,
    }

    usage = message.usage
    inp = usage.input_tokens or 0
    out = usage.output_tokens or 0
    # Haiku pricing: $0.80/MTok input, $5.00/MTok output
    cost = (inp * 0.0000008) + (out * 0.000005)

    return {
        "output": json.dumps(output),
        "tokenUsage": {"total": inp + out, "prompt": inp, "completion": out},
        "cost": cost,
    }
