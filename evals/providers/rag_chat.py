"""Custom promptfoo provider: rag_generation stage (RAG chat generation eval).

Replays stored system_prompt + user_message from llm_io_logs through
messages.stream (same API as production RAG chat).

Returns structured output {text, context} so promptfoo's built-in
context-faithfulness and answer-relevance metrics can evaluate the response.

Vars expected (written by export_eval_dataset.py --stage rag_generation):
    system_prompt  – full system prompt (RAG context chunks embedded)
    user_message   – full user message (the user's question)
    context        – extracted chunk texts for context-based assertions
    prompt_version – informational only

promptfoo assertion wiring:
    context-faithfulness uses vars.context (or contextTransform: 'JSON.parse(output).context')
    answer-relevance uses JSON.parse(output).text
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

# Delimiter used by prompt_builder.py when embedding chunks in the user message
_DOCUMENT_EXCERPTS_MARKER = "DOCUMENT EXCERPTS:\n\n"
# End at "USER QUESTION:" to capture ALL sources, not just the first chunk
_DOCUMENT_EXCERPTS_END = "\n\nUSER QUESTION:"


def _extract_context_from_system_prompt(system_prompt: str) -> str:
    """Extract chunk text from the system prompt.

    prompt_builder.py embeds chunks as:
        DOCUMENT EXCERPTS:\n\n{context}\n\n---\n\n
    """
    start = system_prompt.find(_DOCUMENT_EXCERPTS_MARKER)
    if start == -1:
        return ""
    start += len(_DOCUMENT_EXCERPTS_MARKER)
    end = system_prompt.find(_DOCUMENT_EXCERPTS_END, start)
    if end == -1:
        return system_prompt[start:].strip()
    return system_prompt[start:end].strip()


def call_api(prompt, options, context):
    import anthropic
    from app.config import settings

    vars_ = context.get("vars", {})
    system_prompt = vars_.get("system_prompt", "")
    user_message = vars_.get("user_message", "")

    if not system_prompt or not user_message:
        return {"error": "Missing system_prompt or user_message in test vars"}

    # Extract context from the actual prompt text (ground truth for what the LLM saw).
    # RAG embeds chunks in user_message under "DOCUMENT EXCERPTS:"; template fill uses system_prompt.
    # Never use vars.context (chunk_texts from DB) — it's a snapshot that may miss chunks.
    context_text = _extract_context_from_system_prompt(user_message)
    if not context_text:
        context_text = _extract_context_from_system_prompt(system_prompt)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        with client.messages.stream(
            model=settings.synthesis_llm_model,
            max_tokens=settings.synthesis_llm_max_tokens,
            temperature=0.0,
            system=[{"type": "text", "text": system_prompt}],
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            message = stream.get_final_message()
    except Exception as exc:
        return {"error": str(exc)}

    if not message.content:
        return {"error": f"Empty response. stop_reason={message.stop_reason}"}

    output_text = message.content[0].text

    usage = message.usage
    inp = usage.input_tokens or 0
    out = usage.output_tokens or 0
    # Haiku pricing: $0.80/MTok input, $5.00/MTok output
    cost = (inp * 0.0000008) + (out * 0.000005)

    return {
        "output": json.dumps({"text": output_text, "context": context_text}),
        "tokenUsage": {"total": inp + out, "prompt": inp, "completion": out},
        "cost": cost,
    }
