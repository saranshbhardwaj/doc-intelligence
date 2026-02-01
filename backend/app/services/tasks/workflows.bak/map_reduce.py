"""Map-Reduce execution for scalable workflow processing.

Implements threshold-based execution:
- Direct execution (≤10K tokens): Single LLM call
- Map-reduce execution (>10K tokens): Section summaries → synthesis

Map-reduce strategy:
1. Phase 1 (Map): Summarize each section independently with cheap model
   - Compress narratives (cost savings)
   - Tables pass through unchanged (preserve fidelity)
   - Validate citations preserved
2. Phase 2 (Reduce): Synthesize summaries into final output with expensive model
"""
from typing import Dict, Any, List
import asyncio

from app.utils.logging import logger
from app.utils.token_utils import count_tokens
from .helpers import _llm, _llm_expensive


def _estimate_token_budget(sections_content: Dict[str, List[Dict]]) -> int:
    """
    Estimate total token budget for all retrieved chunks.

    Uses pre-calculated token_count from chunks (stored during chunking).
    Fallback to character-based estimation if token_count not available.

    Args:
        sections_content: Dict mapping section_key -> list of chunks

    Returns:
        Total estimated tokens across all chunks
    """
    total_tokens = 0

    for section_key, chunks in sections_content.items():
        for chunk in chunks:
            # Use pre-calculated token_count if available
            token_count = chunk.get("token_count")

            if token_count:
                total_tokens += token_count
            else:
                # Fallback: estimate from character count (rough 4:1 ratio)
                total_tokens += count_tokens(chunk.get("text", ""))

    return total_tokens


async def _summarize_section(
    section_key: str,
    section_spec: Dict,
    chunks: List[Dict],
    workflow_name: str,
    run_id: str,
    db: Any,
    compressor: Any = None
) -> Dict[str, Any]:
    """
    Summarize a single workflow section (narratives only, tables pass through).

    Strategy:
    1. Split chunks into narrative vs table
    2. Summarize narrative chunks with LLM (cheap model, cached prompt)
    3. Pass table chunks through unchanged (preserve full fidelity)
    4. Validate citations preserved
    5. Save summary to WorkflowRun.section_summaries

    Args:
        section_key: Section identifier (e.g., "financial_performance")
        section_spec: Section specification from retrieval spec
        chunks: Retrieved chunks for this section
        workflow_name: Workflow name for logging
        run_id: Workflow run ID
        db: Database session

    Returns:
        Dict with narrative_summary, table_chunks, citations, token_count
    """
    from app.services.workflows.section_summary_prompt import (
        build_narrative_summary_prompt,
        validate_citations_preserved,
    )
    from app.repositories.workflow_repository import WorkflowRepository

    repo = WorkflowRepository(db)

    # Split chunks by type
    narrative_chunks = [c for c in chunks if not c.get("is_tabular", False)]
    table_chunks = [c for c in chunks if c.get("is_tabular", False)]

    logger.info(
        f"Section '{section_key}': {len(narrative_chunks)} narrative, {len(table_chunks)} table chunks",
        extra={"run_id": run_id, "section_key": section_key}
    )

    # Initialize result structure
    narrative_summary = None
    narrative_key_metrics = []
    narrative_citations = []
    table_key_metrics = []
    table_citations = []

    # Process narrative chunks if present
    if narrative_chunks:
        # No longer compressing chunks before summarization (chunks are already compressed during re-ranking)
        # Send original chunks directly to summarization
        logger.info(
            f"Processing {len(narrative_chunks)} narrative chunks for section '{section_key}'",
            extra={"run_id": run_id, "section_key": section_key}
        )

        # Build summary prompt (returns separate system/user for caching)
        prompt_parts = build_narrative_summary_prompt(
            section_spec,
            narrative_chunks,
            section_key
        )

        # Call LLM with system-level caching (cheap model for summarization)
        llm_client = _llm()

        try:
            logger.info(
                f"Summarizing section '{section_key}': {len(narrative_chunks)} narrative chunks",
                extra={"run_id": run_id, "section_key": section_key}
            )

            # Use cheap model with caching enabled
            # System prompt is cached (100% reuse across all sections)
            response = await llm_client.extract_structured_data(
                text=prompt_parts["user_message"],      # Dynamic chunks
                system_prompt=prompt_parts["system_prompt"],  # Cached instructions
                use_cache=True  # ✅ Enable caching!
            )

            summary_result = response.get("data", {})

            # Validate citations preserved
            validation = validate_citations_preserved(
                input_chunks=narrative_chunks,
                summary_result=summary_result,
                section_key=section_key,
                run_id=run_id
            )

            # Extract narrative results
            narrative_summary = summary_result.get("summary", "")
            narrative_key_metrics = summary_result.get("key_metrics", [])
            narrative_citations = summary_result.get("citations", [])

            logger.info(
                f"Narrative summary complete for '{section_key}': {len(narrative_key_metrics)} metrics extracted",
                extra={"run_id": run_id, "section_key": section_key}
            )

        except Exception as e:
            logger.error(
                f"Failed to summarize narratives for section '{section_key}': {e}",
                extra={"run_id": run_id, "section_key": section_key},
                exc_info=True
            )

    # Process table chunks if present
    # Keep full tables instead of extracting metrics (preserve all information)
    tables_text = []
    if table_chunks:
        logger.info(
            f"Including {len(table_chunks)} full table chunks for section '{section_key}'",
            extra={"run_id": run_id, "section_key": section_key}
        )

        # Extract citations from table chunks
        for chunk in table_chunks:
            # Add table text
            tables_text.append(chunk.get("text", ""))

            # Extract citation if present (format: [D1:p2])
            metadata = chunk.get("metadata", {})
            citation = metadata.get("citation", "")
            if citation:
                table_citations.append(citation)

    # Combine results from narratives and tables
    all_key_metrics = narrative_key_metrics  # Only from narratives now
    all_citations = list(set(narrative_citations + table_citations))  # Deduplicate

    result = {
        "section_key": section_key,
        "narrative_summary": narrative_summary,
        "tables_text": tables_text,  # Full table chunks (not metrics)
        "citations": all_citations,
        "key_metrics": all_key_metrics,
        "token_count": (
            len(narrative_summary or "") // 4 +  # Estimate narrative tokens
            sum(len(t) // 4 for t in tables_text)  # Estimate table tokens
        )
    }

    # Save to WorkflowRun.section_summaries
    try:
        current_summaries = repo.get_run(run_id).section_summaries or {}
        current_summaries[section_key] = result
        repo.update_run_metadata(run_id, {"section_summaries": current_summaries})
        logger.info(
            f"Saved section summary for '{section_key}' to database",
            extra={"run_id": run_id, "section_key": section_key}
        )
    except Exception as save_err:
        logger.warning(
            f"Failed to save section summary for {section_key}: {save_err}",
            extra={"run_id": run_id, "section_key": section_key}
        )

    logger.info(
        f"Section '{section_key}' complete: {len(narrative_chunks)} narratives + {len(table_chunks)} tables → "
        f"{len(all_key_metrics)} key metrics, {result['token_count']} tokens",
        extra={"run_id": run_id, "section_key": section_key, "result": result}
    )

    return result


async def _execute_map_reduce(
    run_id: str,
    sections_content: Dict[str, List[Dict]],
    workflow_template: Any,
    variables: Dict,
    custom_prompt: str,
    db: Any
) -> Dict[str, Any]:
    """
    Execute map-reduce workflow: section summaries → final synthesis.

    Phase 1 (Map): Summarize each section independently (parallel-capable)
    Phase 2 (Reduce): Synthesize summaries into final output

    Args:
        run_id: Workflow run ID
        sections_content: Dict mapping section_key -> chunks
        workflow_template: Workflow template with retrieval_spec
        variables: Template variables
        custom_prompt: Custom user prompt (optional)
        db: Database session

    Returns:
        LLM result dict with final output
    """
    from app.verticals.private_equity.workflows.templates.investment_memo import get_investment_memo_prompt

    logger.info(
        f"Starting map-reduce execution for {len(sections_content)} sections",
        extra={"run_id": run_id, "section_count": len(sections_content)}
    )

    # Phase 1: Summarize each section (Map)
    section_summaries = {}
    retrieval_spec = workflow_template.retrieval_spec_json or []

    # Parse JSON if it's a string (database stores as JSON)
    if isinstance(retrieval_spec, str):
        import json
        retrieval_spec = json.loads(retrieval_spec)

    for section_spec in retrieval_spec:
        section_key = section_spec.get("key")
        chunks = sections_content.get(section_key, [])

        if not chunks:
            logger.warning(
                f"No chunks for section '{section_key}', skipping",
                extra={"run_id": run_id, "section_key": section_key}
            )
            continue

        # Summarize section
        summary = await _summarize_section(
            section_key=section_key,
            section_spec=section_spec,
            chunks=chunks,
            workflow_name=workflow_template.name,
            run_id=run_id,
            db=db,
            compressor=None  # No longer using compression
        )

        section_summaries[section_key] = summary

    logger.info(
        f"Map phase complete: {len(section_summaries)} sections summarized",
        extra={"run_id": run_id, "summaries": section_summaries.keys()}
    )

    # Phase 2: Synthesize summaries (Reduce)
    synthesis_context = _build_synthesis_context(section_summaries)

    # Build final workflow prompt (returns separate system/user for caching)
    prompt_parts = get_investment_memo_prompt(variables, custom_prompt=custom_prompt)

    # Replace {{CONTEXT}} placeholder with actual synthesis context
    user_message = prompt_parts["user_message"].replace("{{CONTEXT}}", synthesis_context)

    logger.info(
        f"Starting synthesis with {len(synthesis_context)} chars",
        extra={"run_id": run_id, "synthesis_context_length": len(synthesis_context)}
    )

    # Call LLM for final synthesis using synthesis-specific model (Haiku 4.5)
    llm_client = _llm_expensive()

    # Validate output schema is present
    if not workflow_template.output_schema:
        error_msg = "Workflow missing output_schema - cannot generate structured output"
        logger.error(error_msg, extra={"run_id": run_id, "workflow_id": workflow_template.id})
        raise ValueError(error_msg)

    synthesis_result = await llm_client.extract_structured_data(
        text=user_message,
        system_prompt=prompt_parts["system_prompt"],
        context=workflow_template.output_schema,
        use_cache=True
    )

    logger.info(
        f"Map-reduce synthesis complete",
        extra={
            "run_id": run_id,
            "output_length": len(synthesis_result.get('raw_text', ''))
        }
    )

    return synthesis_result


def _build_synthesis_context(section_summaries: Dict[str, Dict]) -> str:
    """
    Build context for final synthesis from section summaries.

    Combines narrative summaries + full table chunks (preserving all information).
    No longer extracts metrics from tables - sends full table content.

    Args:
        section_summaries: Dict of section_key -> summary dict

    Returns:
        Formatted context string for synthesis
    """
    context_parts = []

    for section_key, summary in section_summaries.items():
        section_title = section_key.replace("_", " ").title()

        # Add narrative summary if present
        narrative_summary = summary.get("narrative_summary")
        if narrative_summary:
            context_parts.append(f"## {section_title}\n\n{narrative_summary}")

        # Add key metrics from narratives (if any)
        key_metrics = summary.get("key_metrics", [])
        if key_metrics:
            context_parts.append(f"\n### Key Metrics - {section_title}\n")
            for metric in key_metrics:
                metric_name = metric.get("metric", "Unknown")
                metric_value = metric.get("value", "N/A")
                citation = metric.get("citation", "")
                context_parts.append(f"- **{metric_name}**: {metric_value} {citation}")

        # Add full table chunks (preserving all table information)
        tables_text = summary.get("tables_text", [])
        if tables_text:
            context_parts.append(f"\n### Tables - {section_title}\n")
            for i, table_text in enumerate(tables_text, 1):
                context_parts.append(f"\n{table_text}\n")

    return "\n\n".join(context_parts)
