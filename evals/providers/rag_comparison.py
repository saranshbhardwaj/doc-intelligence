"""Custom promptfoo provider: rag_comparison stage.

Replays stored comparison prompts from llm_io_logs (stage=rag_chat_comparison).

Comparison flow uses a single prompt string (not split into system/user like regular
RAG chat) — matching production behavior in comparison_flow.py which calls
stream_chat(prompt) with no system_prompt argument.

Returns structured output {text, context} for context-faithfulness assertions.
The context is derived from the stored comparison prompt so the judge sees the
same evidence the model saw during the original comparison run.

Vars expected (written by export_eval_dataset.py --stage rag_comparison):
    system_prompt  – full comparison prompt (single string, includes chunks + instructions)
    user_message   – raw user question
    context        – extracted chunk texts for context-based assertions
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

_COMPARISON_CONTEXT_MARKERS = (
    "\n## Paired Content",
    "\n## Clustered Content",
    "\n## Extracted Facts by Document",
)
_COMPARISON_CONTEXT_END_MARKERS = (
    "\n## Comparison Focus",
    "\n" + "=" * 80,
)
_COMPARISON_VALIDATION_HEADER = (
    "ADDITIONAL COMPARISON VALIDATION RULES:\n"
    "- Treat each metric label literally. Never substitute NOI for Gross Potential Rent, "
    "rent for NOI, current for year-one, or pro forma for current unless the cited value is explicitly labeled that way.\n"
    "- Only compare, rank, or recommend on metrics explicitly disclosed for the relevant document. "
    "If a metric is missing for any document, write **Not disclosed** and say that the direct comparison is limited.\n"
    "- For period-specific comparisons such as Current, Year One, and Pro Forma, only include a row when that exact "
    "metric-period pair is explicitly present for every document. Otherwise omit the row or mark the missing value as "
    "**Not disclosed**. Never fill a missing period from NOI, cap rate, or any other different metric.\n"
    "- Do not infer undisclosed metrics or unsupported qualitative claims such as execution risk, "
    "cash-on-cash superiority, or upside superiority unless the prompt gives direct evidence.\n"
    "- Before stating higher, lower, better, worse, or more upside, verify the cited numbers support that exact direction.\n"
)


def _extract_context_from_comparison_prompt(prompt_text: str) -> str:
    """Extract the prompt-visible comparison evidence from the stored prompt."""
    if not prompt_text:
        return ""

    for marker in _COMPARISON_CONTEXT_MARKERS:
        start = prompt_text.find(marker)
        if start == -1:
            continue

        start += len(marker)
        end_candidates = [
            prompt_text.find(end_marker, start)
            for end_marker in _COMPARISON_CONTEXT_END_MARKERS
            if prompt_text.find(end_marker, start) != -1
        ]
        end = min(end_candidates) if end_candidates else len(prompt_text)
        return prompt_text[start:end].strip()

    return ""


def _apply_comparison_guardrails(prompt_text: str) -> str:
    if not prompt_text:
        return prompt_text

    if _COMPARISON_VALIDATION_HEADER in prompt_text:
        return prompt_text

    return f"{_COMPARISON_VALIDATION_HEADER}\n{prompt_text}"


def call_api(prompt, options, context):
    import anthropic
    vars_ = context.get("vars", {})
    # In comparison mode, the full prompt (instructions + paired chunks) is stored
    # as system_prompt. We send it as the user message to match stream_chat(prompt).
    full_prompt = _apply_comparison_guardrails(vars_.get("system_prompt", ""))

    if not full_prompt:
        return {"error": "Missing system_prompt (comparison prompt) in test vars"}

    context_text = _extract_context_from_comparison_prompt(full_prompt) or vars_.get("context", "").strip()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("EVAL_RAG_MODEL", "claude-haiku-4-5-20251001")
    max_tokens = int(os.environ.get("EVAL_RAG_MAX_TOKENS", "4096"))

    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set in evals/.env"}

    client = anthropic.Anthropic(api_key=api_key)

    try:
        # Send the full prompt as user content — no system_prompt split
        # (matches production: comparison_flow.py → llm_client.stream_chat(prompt))
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            temperature=0.0,
            system=_COMPARISON_VALIDATION_HEADER,
            messages=[{"role": "user", "content": full_prompt}],
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
