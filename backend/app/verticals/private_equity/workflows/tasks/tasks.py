"""Celery tasks for workflow execution pipeline.

Unified Pipeline (Single-Doc & Multi-Doc):
1. Hybrid retrieval (semantic + keyword search)
2. Chunk processing (compression/truncation for re-ranker compatibility)
3. Cross-encoder re-ranking (skip for large tables, preserve full content)
4. Diversity filtering (max 50% from one document)
5. Section-based context assembly
6. LLM generation with workflow-specific prompts

The pipeline uses targeted retrieval for both single and multi-doc workflows,
ensuring consistent quality and efficient context assembly.

Task Flow:
- prepare_context_task: Retrieves and assembles context
- generate_artifact_task: Generates LLM output with validation
- start_workflow_chain: Orchestrates the task chain
"""
from __future__ import annotations
from celery import shared_task, chain
from typing import Dict, Any, List, Tuple
import asyncio
import json
import re
import time

from app.database import get_db
from app.repositories.workflow_repository import WorkflowRepository
from app.repositories.collection_repository import CollectionRepository
from app.services.llm_client import LLMClient
from jsonschema import Draft202012Validator
from app.verticals.private_equity.workflows.schemas.investment_memo_schema import InvestmentMemo
from app.verticals.private_equity.workflows.validator import validate_output
from app.services.job_tracker import JobProgressTracker
from app.utils.logging import logger
from app.config import settings
from app.db_models_workflows import WorkflowRun, Workflow
from app.db_models_chat import DocumentChunk, CollectionDocument
from sqlalchemy import text as sql_text, select
from app.core.embeddings import get_embedding_provider
from app.core.rag.workflow_retriever import WorkflowRetriever
from app.utils.costs import compute_llm_cost
from app.services.artifacts import persist_artifact
from app.verticals.private_equity.workflows.normalization import normalize_workflow_output
from app.utils.metrics import (
    WORKFLOW_RUNS_COMPLETED,
    WORKFLOW_RUNS_FAILED,
    WORKFLOW_RUNS_PARTIAL,
    WORKFLOW_LATENCY_SECONDS,
)
from app.utils.file_utils import save_raw_llm_response

# Import from our new modules
from .helpers import (
    _llm_expensive,
    normalize_llm_output,
    handle_llm_result,
    _get_db_session,
    _llm,
    validate_investment_memo_constraints
)
from .map_reduce import (
    _estimate_token_budget,
    _execute_map_reduce,
)


@shared_task(bind=True)
def prepare_context_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble context for workflow run.
    Lightweight retrieval placeholder (top N chunks per doc).
    """
    start = time.time()  # Track latency for context preparation
    run_id = payload["run_id"]
    job_id = payload.get("job_id")
    db = _get_db_session()
    repo = WorkflowRepository(db)
    run = repo.get_run(run_id)
    if not run:
        logger.error("WorkflowRun not found", extra={"run_id": run_id})
        return {"status": "failed", "error": "run_not_found", **payload}

    tracker = JobProgressTracker(db, job_id) if job_id else JobProgressTracker(db, run_id)  # Fallback to run_id if job missing
    tracker.update_progress(status="context", current_stage="context", progress_percent=10, message="Building workflow context")

    try:
        # Handle both old data (JSON strings) and new data (Python objects)
        doc_ids_raw = run.document_ids
        if isinstance(doc_ids_raw, str):
            doc_ids = json.loads(doc_ids_raw or "[]")
        else:
            doc_ids = doc_ids_raw or []
        context_sections: List[str] = []

        # Strategy: Use workflow-specific retrieval with hybrid search + cross-encoder re-ranking
        # Always uses targeted retrieval
        try:
            # Get workflow-specific retrieval spec
            workflow = run.workflow

            # Load retrieval spec from workflow (if available)
            if hasattr(workflow, 'retrieval_spec_json') and workflow.retrieval_spec_json:
                # Workflow has custom retrieval spec stored in database
                sections_spec = json.loads(workflow.retrieval_spec_json)
                logger.info(f"Using workflow-specific retrieval spec: {len(sections_spec)} sections")
            else:
                # Fall back to generic sections (backwards compatibility)
                sections_spec = [
                    {
                        "key": "executive",
                        "title": "EXECUTIVE OVERVIEW",
                        "queries": ["investment highlights", "key strengths", "business overview"],
                        "prefer_tables": False,
                        "max_chunks": 15
                    },
                    {
                        "key": "market",
                        "title": "MARKET & COMPETITION",
                        "queries": ["market size", "competitive landscape", "growth drivers", "competition"],
                        "prefer_tables": False,
                        "max_chunks": 15
                    },
                    {
                        "key": "financial",
                        "title": "FINANCIAL HIGHLIGHTS",
                        "queries": ["revenue growth", "ebitda margin", "financial performance", "profitability"],
                        "prefer_tables": True,
                        "max_chunks": 20
                    },
                    {
                        "key": "risks",
                        "title": "RISKS",
                        "queries": ["risk factors", "customer concentration", "regulatory risk", "operational risk"],
                        "prefer_tables": False,
                        "max_chunks": 15
                    },
                    {
                        "key": "actions",
                        "title": "RECOMMENDED ACTIONS",
                        "queries": ["recommended actions", "follow-up diligence", "next steps"],
                        "prefer_tables": False,
                        "max_chunks": 10
                    },
                ]
                logger.warning(f"No retrieval spec found for workflow {workflow.name}, using generic")

            # Initialize workflow retriever (hybrid + re-ranking + compression)
            workflow_retriever = WorkflowRetriever(db)

            # Retrieve all sections
            sections_content = workflow_retriever.retrieve_all_sections(
                sections_spec=sections_spec,
                document_ids=doc_ids
            )

            # ========== CRITICAL: Validate chunks were retrieved ==========
            total_chunks = sum(len(chunks) for chunks in sections_content.values())
            if total_chunks == 0:
                error_msg = "No chunks retrieved from documents. Documents may not be indexed or retrieval failed."
                logger.error(error_msg, extra={"run_id": run_id, "document_ids": doc_ids})
                repo.update_run_status(
                    run_id,
                    status="failed",
                    error_message=error_msg,
                    latency_ms=int((time.time()-start)*1000)
                )
                tracker.mark_error(error_stage="context", error_message=error_msg, error_type="no_chunks_retrieved", is_retryable=False)
                return {"status": "failed", "run_id": run_id, "job_id": job_id, "error": "no_chunks_retrieved"}

            # ========== THRESHOLD-BASED EXECUTION: Direct vs Map-Reduce ==========
            # Estimate token budget to decide execution strategy
            total_tokens = _estimate_token_budget(sections_content)

            # Threshold: 20K tokens
            # ≤ 20K tokens → Direct execution (single LLM call with all sections)
            # > 20K tokens → Map-reduce execution (section summaries → synthesis)
            # use_map_reduce = True
            use_map_reduce = total_tokens > 10000

            logger.info(
                f"Token budget: {total_tokens} tokens, execution_mode={'map_reduce' if use_map_reduce else 'direct'}",
                extra={
                    "run_id": run_id,
                    "total_tokens": total_tokens,
                    "execution_mode": "map_reduce" if use_map_reduce else "direct",
                    "sections_count": len(sections_content)
                }
            )

            # Store sections_content and workflow in payload for generate_artifact_task
            # (needed for map-reduce execution)
            payload["sections_content"] = sections_content
            payload["use_map_reduce"] = use_map_reduce
            payload["total_tokens"] = total_tokens
            payload["workflow_id"] = workflow.id  # Pass workflow ID for retrieval in next task

            # Format sections for context (only for direct execution)
            # For map-reduce, compression happens later in _summarize_section
            if not use_map_reduce:
                # Direct execution: Compress ALL narrative chunks now
                from app.core.rag.chunk_compressor import ChunkCompressor
                compressor = ChunkCompressor()

                for spec in sections_spec:
                    section_key = spec["key"]
                    section_title = spec["title"]
                    chunks = sections_content.get(section_key, [])

                    if not chunks:
                        logger.debug(f"No content retrieved for section: {section_title}")
                        continue

                    # Split by type
                    narrative_chunks = [c for c in chunks if not c.get("is_tabular", False)]
                    table_chunks = [c for c in chunks if c.get("is_tabular", False)]

                    # Compress ALL narratives (for LLM cost savings)
                    if narrative_chunks:
                        narrative_chunks = compressor.compress_chunks(narrative_chunks)
                        logger.debug(f"Compressed {len(narrative_chunks)} narrative chunks for section {section_key}")

                    # Combine back (narratives now have compressed_text field)
                    all_chunks = narrative_chunks + table_chunks

                    context_sections.append(f"=== SECTION: {section_title} ===")
                    for chunk in all_chunks:
                        citation = chunk.get("citation", "[?]")
                        # Use compressed_text for narratives, text for tables
                        text = chunk.get("compressed_text") or chunk.get("text", "")
                        context_sections.append(f"{citation} {text}")
            else:
                # Map-reduce: Don't compress here, will compress in _summarize_section
                logger.info("Map-reduce mode: skipping compression in context assembly (will compress per section)")
                for spec in sections_spec:
                    section_key = spec["key"]
                    section_title = spec["title"]
                    chunks = sections_content.get(section_key, [])

                    if not chunks:
                        continue

                    context_sections.append(f"=== SECTION: {section_title} ===")
                    for chunk in chunks:
                        citation = chunk.get("citation", "[?]")
                        text = chunk.get("text", "")  # Original text for map-reduce
                        context_sections.append(f"{citation} {text}")

            # ========== BUILD CITATION MAP ==========
            # Build citation map from retrieved chunks to avoid DB queries during resolution
            citation_map = {}
            for section_key, chunks in sections_content.items():
                for chunk in chunks:
                    citation_token = chunk.get("citation")
                    if citation_token:
                        # Build rich citation metadata from chunk data
                        chunk_metadata = chunk.get("chunk_metadata") or {}
                        citation_map[citation_token] = {
                            "id": citation_token,
                            "token": citation_token,
                            "document": chunk_metadata.get("document_filename") or chunk.get("document_id", "Unknown"),
                            "page": chunk.get("page_number"),
                            "section": chunk_metadata.get("section_heading") or chunk.get("section_heading"),
                            "snippet": chunk_metadata.get("first_sentence") or (chunk.get("text", "")[:200] + "..." if len(chunk.get("text", "")) > 200 else chunk.get("text", "")),
                            "heading_hierarchy": chunk_metadata.get("heading_hierarchy", []),
                            "url": f"/api/documents/{chunk.get('document_id')}/download" if chunk.get('document_id') else None,
                        }

            logger.info(
                f"Workflow retrieval complete: {len(sections_content)} sections, "
                f"{sum(len(chunks) for chunks in sections_content.values())} total chunks, "
                f"{len(citation_map)} unique citations mapped"
            )

            # DEBUG: Log sample citation from map
            if citation_map:
                sample_citation_token = list(citation_map.keys())[0]
                sample_citation_data = citation_map[sample_citation_token]
                logger.info(
                    f"📍 Citation map sample: {sample_citation_token} → "
                    f"{{document: {sample_citation_data.get('document')}, "
                    f"page: {sample_citation_data.get('page')}, "
                    f"snippet: {sample_citation_data.get('snippet', '')[:50]}...}}"
                )

            # Store citation map in payload for resolution (NO DB queries needed!)
            payload["citation_map"] = citation_map

        except Exception as retrieval_err:
            # If any error occurred during retrieval, rollback and fallback
            try:
                db.rollback()
            except Exception:
                pass
            logger.error(
                "Workflow retrieval failed, falling back to sampling",
                extra={"error": str(retrieval_err), "error_type": type(retrieval_err).__name__},
                exc_info=True
            )
            # Fallback: Simple sampling (use first 30 chunks per doc)
            for idx, doc_id in enumerate(doc_ids):
                chunks = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == doc_id
                ).order_by(DocumentChunk.chunk_index.asc()).limit(30).all()
                context_sections.append(f"=== DOCUMENT {idx+1} ({doc_id}) SAMPLE CHUNKS ===")
                for c in chunks:
                    prefix = f"[D{idx+1}:p{c.page_number}]"
                    context_sections.append(f"{prefix} {c.text[:1000]}")

        combined_context = "\n".join(context_sections)

        # Budget enforcement: Check context size
        context_char_count = len(combined_context)
        if context_char_count > settings.workflow_context_max_chars:
            logger.warning("Context exceeds max chars limit", extra={"run_id": run_id, "chars": context_char_count, "limit": settings.workflow_context_max_chars})
            # Truncate context to fit budget (keep first 80% and last 20% for continuity)
            truncate_point = int(settings.workflow_context_max_chars * 0.8)
            tail_start = len(combined_context) - int(settings.workflow_context_max_chars * 0.2)
            combined_context = combined_context[:truncate_point] + "\n\n[... CONTEXT TRUNCATED FOR BUDGET ...]\n\n" + combined_context[tail_start:]
            logger.info("Context truncated to fit budget", extra={"run_id": run_id, "new_chars": len(combined_context)})

        tracker.update_progress(progress_percent=35, message="Context assembled", context_completed=True)
        return {**payload, "combined_context": combined_context, "job_id": job_id}
    except Exception as e:
        logger.exception("Failed to prepare context", extra={"run_id": run_id})
        # Ensure DB session is clean before attempting to update run status
        try:
            db.rollback()
        except Exception:
            pass
        try:
            repo.update_run_status(run_id, status="failed", error_message=str(e))
        except Exception:
            logger.exception("Failed to update run status after prepare_context failure", extra={"run_id": run_id})
        return {"status": "failed", "error": "context_error", **payload}
    finally:
        db.close()


@shared_task(bind=True)
def generate_artifact_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate workflow artifact using LLM and store result."""
    run_id = payload["run_id"]
    job_id = payload.get("job_id")
    combined_context = payload.get("combined_context", "")
    db = _get_db_session()
    repo = WorkflowRepository(db)
    run = repo.get_run(run_id)
    if not run:
        return {"status": "failed", "error": "run_not_found", **payload}

    tracker = JobProgressTracker(db, job_id) if job_id else JobProgressTracker(db, run_id)
    tracker.update_progress(status="generating", current_stage="generating", progress_percent=50, message="Generating artifact")
    start = time.time()

    try:
        # record latency for the generation phase
        timer = WORKFLOW_LATENCY_SECONDS.time()
        timer.__enter__()
        workflow = run.workflow

        # Get workflow name from snapshot (preferred) or relationship (fallback)
        # Snapshot is more reliable and persists even if template is deleted
        workflow_name = None
        if run.workflow_snapshot and isinstance(run.workflow_snapshot, dict):
            workflow_name = run.workflow_snapshot.get("name")
        if not workflow_name and workflow:
            workflow_name = workflow.name
        if not workflow_name:
            workflow_name = "Unknown Workflow"
            logger.warning(
                f"Could not determine workflow name for run {run_id}",
                extra={"run_id": run_id, "workflow_id": run.workflow_id}
            )

        # Handle both old data (JSON strings) and new data (Python objects)
        variables_raw = run.variables
        if isinstance(variables_raw, str):
            variables = json.loads(variables_raw or "{}")
        else:
            variables = variables_raw or {}

        # Check if user provided custom prompt (from UI)
        custom_prompt = payload.get("custom_prompt")

        # ========== WORKFLOW PROMPT GENERATORS REGISTRY ==========
        # All workflows must implement a prompt_generator function
        # that returns {"system_prompt": str, "user_message": str} for caching support
        from app.verticals.private_equity.workflows.templates.investment_memo import get_investment_memo_prompt

        PROMPT_GENERATORS = {
            "Investment Memo": get_investment_memo_prompt,
            # "Red Flag Analysis": get_red_flag_prompt,  # Add when ready
            # "Financial Analysis": get_financials_prompt,  # Add when ready
        }

        # Get prompt generator for this workflow
        prompt_generator = PROMPT_GENERATORS.get(workflow.name)
        if not prompt_generator:
            error_msg = f"Workflow '{workflow.name}' has no prompt_generator implementation. All workflows must use caching-optimized architecture."
            logger.error(error_msg, extra={"run_id": run_id, "workflow_name": workflow.name})
            repo.update_run_status(run_id, status="failed", error_message=error_msg)
            tracker.mark_error(error_stage="generating", error_message=error_msg, error_type="no_prompt_generator", is_retryable=False)
            return {"status": "failed", "error": "no_prompt_generator", **payload}

        # Generate prompt using caching-optimized architecture
        try:
            logger.info(f"Calling prompt generator for '{workflow.name}'", extra={
                "run_id": run_id,
                "workflow_name": workflow.name,
                "variables_keys": list(variables.keys()) if isinstance(variables, dict) else "not a dict",
                "custom_prompt_length": len(custom_prompt) if custom_prompt else 0,
                "has_custom_prompt": bool(custom_prompt)
            })

            rendered_template = prompt_generator(variables, custom_prompt=custom_prompt)

            # Validate return type
            if not isinstance(rendered_template, dict) or "system_prompt" not in rendered_template or "user_message" not in rendered_template:
                raise ValueError(f"prompt_generator must return dict with 'system_prompt' and 'user_message' keys. Got: {type(rendered_template)}")

            workflow_system_prompt = rendered_template["system_prompt"]
            workflow_user_template = rendered_template["user_message"]
            use_caching = True  # Always enabled with new architecture

            logger.info("Prompt generated successfully", extra={
                "run_id": run_id,
                "workflow_name": workflow.name,
                "system_prompt_length": len(workflow_system_prompt),
                "user_template_length": len(workflow_user_template),
                "caching_enabled": use_caching
            })

        except Exception as e:
            error_msg = f"Prompt generation failed: {e}"
            logger.error(error_msg, extra={
                "run_id": run_id,
                "workflow_name": workflow.name,
                "error": str(e)
            }, exc_info=True)
            repo.update_run_status(run_id, status="failed", error_message=error_msg)
            tracker.mark_error(error_stage="generating", error_message=error_msg, error_type="prompt_generation_error", is_retryable=False)
            return {"status": "failed", "error": "prompt_generation_failed", **payload}

        # Safety check: ensure workflow_system_prompt is a string
        if not isinstance(workflow_system_prompt, str):
            logger.error(f"workflow_system_prompt is not a string: {type(workflow_system_prompt)}, value: {workflow_system_prompt}")
            raise ValueError(f"workflow_system_prompt must be a string, got {type(workflow_system_prompt)}")

        if not workflow_system_prompt.strip():
            logger.error("workflow_system_prompt is empty after rendering")
            raise ValueError("workflow_system_prompt cannot be empty")

        logger.info(f"Workflow system prompt ready: {len(workflow_system_prompt)} chars, caching={use_caching}", extra={"run_id": run_id})

        llm_client = _llm_expensive()
        model_name = settings.synthesis_llm_model

        # ---------------- Citation & JSON Validation Loop ----------------
        allowed_citations = set(re.findall(r"\[D\d+:p\d+\]", combined_context))

        last_invalid_reason = ""
        final_json = None
        raw_response = None
        used_citations: List[str] = []
        invalid_citations: List[str] = []
        validation_errors: List[dict] = []  # Initialize validation_errors before loop
        last_parsed_candidate = None  # keep most recent parsed_candidate even if invalid
        usage_meta = {}  # Initialize to prevent UnboundLocalError when all LLM attempts fail

        citation_snippets = {}
        for line in combined_context.splitlines():
            found = re.findall(r"\[D\d+:p\d+\]", line)
            if not found:
                continue
            remainder = re.sub(r"\[D\d+:p\d+\]\s*", "", line).strip()
            for c in found:
                if c not in citation_snippets and remainder:
                    citation_snippets[c] = remainder[:500]

        # Track the current system prompt (will be updated on retries with corrective feedback)
        current_system_prompt = workflow_system_prompt

        # ========== EXECUTION ROUTING: Direct vs Map-Reduce ==========
        use_map_reduce = payload.get("use_map_reduce", False)
        attempt = 0  # Initialize for both paths (incremented in direct execution loop)

        if use_map_reduce:
            # Map-Reduce Execution: Section summaries → synthesis
            logger.info(
                f"Using map-reduce execution (tokens={payload.get('total_tokens')})",
                extra={"run_id": run_id, "execution_mode": "map_reduce"}
            )

            try:
                sections_content = payload.get("sections_content", {})

                # Execute map-reduce with custom_prompt
                llm_result = asyncio.run(
                    _execute_map_reduce(
                        run_id=run_id,
                        sections_content=sections_content,
                        workflow_template=workflow,
                        variables=variables,
                        custom_prompt=custom_prompt,
                        db=db
                    )
                )

                if not llm_result.get("data"):
                    # Hard fail - SDK couldn't parse
                    # No salvage possible with structured outputs
                    tracker.mark_error(
                        error_stage="generating",
                        error_message=llm_result.get("error", "SDK parsing failed"),
                        error_type="validation_error",
                        is_retryable=True  # Retry might work (LLM non-determinism)
                    )
                    return {"status": "failed", "run_id": run_id, "job_id": job_id}

                # Process result (same as direct execution)
                info = handle_llm_result(run_id, combined_context, llm_result)
                raw_response = info["raw_text"]
                final_json = info["parsed_candidate"]
                usage_meta = info["usage_meta"]
                used_citations = info["used_citations"]
                invalid_citations = info["invalid_citations"]

                logger.info(
                    f"Map-reduce execution complete: {len(raw_response)} chars",
                    extra={"run_id": run_id, "citations": len(used_citations)}
                )

            except Exception as map_reduce_err:
                logger.error(
                    f"Map-reduce execution failed: {map_reduce_err}",
                    extra={"run_id": run_id},
                    exc_info=True
                )
                repo.update_run_status(run_id, status="failed", error_message=f"Map-reduce error: {map_reduce_err}")
                tracker.mark_error(error_stage="generating", error_message=str(map_reduce_err), error_type="map_reduce_error", is_retryable=True)
                return {"status": "failed", "error": "map_reduce_failed", **payload}

        else:
            # Direct Execution: Single LLM call with all sections (existing flow)
            logger.info(
                f"Using direct execution (tokens={payload.get('total_tokens', 'unknown')})",
                extra={"run_id": run_id, "execution_mode": "direct"}
            )
                
            try:
                # Validate output schema is present
                if not workflow.output_schema:
                    error_msg = "Workflow missing output_schema - cannot generate structured output"
                    logger.error(error_msg, extra={"run_id": run_id, "workflow_id": workflow.id})
                    repo.update_run_status(run_id, status="failed", error_message=error_msg)
                    tracker.mark_error(error_stage="generating", error_message=error_msg, error_type="configuration_error", is_retryable=False)
                    return {"status": "failed", "error": "missing_schema", **payload}

                # Build user message with context
                user_message = workflow_user_template.replace("{{CONTEXT}}", combined_context)

                # Single LLM call with JSON schema in context
                llm_result = asyncio.run(
                    llm_client.extract_structured_data_with_schema(
                        text=user_message,
                        system_prompt=current_system_prompt,
                        pydantic_model=InvestmentMemo,
                        use_cache=use_caching
                    )
                )

                raw_response = llm_result["raw_text"]
                final_json = llm_result["data"]
                usage_meta = llm_result["usage"]

                # Validate citations
                used_citations = list(set(re.findall(r"\[D\d+:p\d+\]", raw_response)))
                invalid_citations = [c for c in used_citations if c not in allowed_citations]

                validation_errors = []
                if invalid_citations:
                    validation_errors.append({
                        "code": "citation_invalid",
                        "message": f"Found {len(invalid_citations)} invalid citations",
                        "invalid_citations": invalid_citations[:10]
                    })

                citation_count = len(used_citations)

                logger.info(
                    f"Direct generation complete",
                    extra={
                        "run_id": run_id,
                        "citations": citation_count,
                        "invalid_citations": len(invalid_citations),
                        "warnings": len([e for e in validation_errors if e.get("severity") == "warning"])
                    }
                )

            except Exception as e:
                logger.error(f"Direct generation failed: {e}", extra={"run_id": run_id})
                repo.update_run_status(run_id, status="failed", error_message=str(e))
                tracker.mark_error(error_stage="generating", error_message=str(e), error_type="llm_error", is_retryable=True)
                return {"status": "failed", "error": "generation_error", **payload}
        # Safety check: If all attempts failed and we have no response, fail gracefully
        if raw_response is None:
            logger.error(f"All LLM attempts failed, no valid response received", extra={"run_id": run_id, "last_error": last_invalid_reason})
            repo.update_run_status(run_id, status="failed", error_message=last_invalid_reason or "All LLM attempts failed")
            tracker.mark_error(error_stage="generating", error_message=last_invalid_reason or "All LLM attempts failed", error_type="llm_error", is_retryable=True)
            return {"status": "failed", "error": "generation_error", **payload}

        # ---- Normalize LLM Output (comprehensive normalization) ----
        logger.info("Normalizing LLM output before schema validation", extra={"run_id": run_id})
        # First apply simple normalization (existing function)
        final_json = normalize_llm_output(final_json, workflow.name)
        # Then apply comprehensive workflow-specific normalization with rich citations
        currency = final_json.get("currency", "USD")

        # Handle both old data (JSON strings) and new data (Python objects) for doc_ids
        doc_ids_raw = run.document_ids
        if isinstance(doc_ids_raw, str):
            doc_ids = json.loads(doc_ids_raw or "[]")
        else:
            doc_ids = doc_ids_raw or []

        # Get citation map from payload (built during retrieval, zero DB queries!)
        citation_map = payload.get("citation_map", {})

        final_json = normalize_workflow_output(
            final_json,
            workflow.name,
            currency=currency,
            document_ids=doc_ids,
            db=db,
            raw_text=raw_response,
            citation_map=citation_map  # Pass citation map for zero-DB resolution
        )

        # Custom validation for constraints SDK can't enforce
        custom_validation = validate_investment_memo_constraints(final_json)

        validation_info = {
            "attempts": attempt + 1,
            "citation_count": len(used_citations),
            "invalid_citations": invalid_citations,
            "allowed_citations_sample": list(sorted(allowed_citations))[:40],
            "last_invalid_reason": last_invalid_reason,
            "finalized": True,
            "sdk_validated": True,
            "custom_validation_warnings": len(custom_validation["issues"]),
            "token_usage": usage_meta,
        }

        # Log warnings (don't fail on these)
        if custom_validation["issues"]:
            logger.warning(
                "Constraint validation warnings",
                extra={"run_id": run_id, "issues": custom_validation["issues"]}
            )

        # Fail on hard errors
        if not custom_validation["valid"]:
            validation_errors.extend(custom_validation["errors"])
            
            # Add to artifact and fail
            repo.update_run_status(
                run_id,
                status="failed",
                error_message=f"Constraint validation failed: {custom_validation['errors']}",
                validation_errors_json=json.dumps(validation_errors),
            )
            tracker.mark_error(
                error_stage="generating",
                error_message="Custom constraint validation failed",
                error_type="validation_error",
                is_retryable=True  # Retry - LLM might get it right next time
            )
            return {"status": "failed", "run_id": run_id, "job_id": job_id}

        # Build rich citations list for frontend (not part of schema-validated output)
        rich_citations = []
        if citation_map and "references" in final_json:
            for token in final_json["references"]:
                citation_data = citation_map.get(token)
                if citation_data:
                    rich_citations.append(citation_data)
                else:
                    # Fallback if token not in map
                    rich_citations.append({
                        "id": token,
                        "token": token,
                        "document": "Unknown",
                        "page": None,
                        "section": None,
                        "snippet": token,
                        "url": None
                    })
            logger.info(f"Built rich_citations list: {len(rich_citations)} citations with metadata")

        artifact = {
            "raw": raw_response,
            "parsed": final_json,
            "validation": validation_info,
            "errors": validation_errors,
            "citation_snippets": citation_snippets,  # OLD format (keep for now)
            "rich_citations": rich_citations  # NEW format with metadata
        }

        input_tokens = usage_meta.get("input_tokens") or 0
        output_tokens = usage_meta.get("output_tokens") or 0
        total_tokens = input_tokens + output_tokens
        cost_usd = compute_llm_cost(model_name, input_tokens, output_tokens) if total_tokens else None

        # Budget enforcement: Check if limits exceeded (log warning but don't fail)
        if total_tokens > settings.workflow_max_tokens_per_run:
            logger.warning("Workflow run exceeded token budget", extra={
                "run_id": run_id,
                "tokens_used": total_tokens,
                "budget": settings.workflow_max_tokens_per_run
            })
        if cost_usd and cost_usd > settings.workflow_max_cost_per_run_usd:
            logger.warning("Workflow run exceeded cost budget", extra={
                "run_id": run_id,
                "cost_usd": cost_usd,
                "budget_usd": settings.workflow_max_cost_per_run_usd
            })

        artifact_ptr = persist_artifact(run_id, artifact, workflow_name=workflow_name, created_at=run.created_at)
        artifact_record = dict(artifact_ptr)
        artifact_record["summary"] = {
            "finalized": True,
            "partial": False,
            "attempts": attempt + 1,
            "citation_count": len(used_citations),
            "invalid_citations_count": len(invalid_citations),
            "schema_error_count": validation_info.get("schema_error_count", 0),
            "model": model_name,
            "format": workflow.output_format,
        }

        # Extract currency from artifact (if present in top-level or financials)
        currency = None
        if isinstance(artifact, dict):
            currency = artifact.get("currency")
            if not currency and "financials" in artifact and isinstance(artifact["financials"], dict):
                currency = artifact["financials"].get("currency")

        repo.update_run_status(
            run_id,
            status="completed",
            artifact_json=artifact_record,
            latency_ms=int((time.time()-start)*1000),
            citations_count=len(used_citations),
            citation_invalid_count=len(invalid_citations),
            attempts=attempt+1,
            validation_errors_json=json.dumps(validation_errors),
            token_usage=total_tokens if total_tokens else None,
            cost_usd=cost_usd,
            currency=currency
        )
        WORKFLOW_RUNS_COMPLETED.inc()
        # stop timer
        try:
            timer.__exit__(None, None, None)
        except Exception:
            pass
        tracker.update_progress(progress_percent=100, message="Artifact generated & validated", artifact_completed=True, validation_completed=True)
        tracker.mark_completed()
        return {"status": "completed", "run_id": run_id, "job_id": job_id}
    except Exception as e:
        # Rollback session to clear any aborted transaction before DB writes
        try:
            db.rollback()
        except Exception:
            pass
        try:
            repo.update_run_status(run_id, status="failed", error_message=str(e))
        except Exception:
            logger.exception("Failed to update run status after generation failure", extra={"run_id": run_id})
        try:
            tracker.mark_error(error_stage="generating", error_message=str(e), error_type="llm_error", is_retryable=True)
        except Exception:
            logger.exception("Failed to mark job error after generation failure", extra={"run_id": run_id})
        return {"status": "failed", "error": "generation_error", **payload}
    finally:
        db.close()


def start_workflow_chain(run_id: str, job_id: str | None, custom_prompt: str | None = None):
    """Kick off workflow execution chain."""
    payload = {"run_id": run_id, "job_id": job_id}
    if custom_prompt:
        payload["custom_prompt"] = custom_prompt
    task_chain = chain(
        prepare_context_task.s(payload),
        generate_artifact_task.s(),
    )
    result = task_chain.apply_async()
    logger.info("Workflow chain started", extra={"run_id": run_id, "task_id": result.id, "custom_prompt_provided": bool(custom_prompt)})
    return result.id
