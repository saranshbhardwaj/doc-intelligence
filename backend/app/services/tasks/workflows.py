"""Celery tasks for workflow execution pipeline.

Pipeline (initial MVP):
Single-doc: parse -> chunk -> summarize (optional) -> generate artifact
Multi-doc: retrieval-based (placeholder) -> generate artifact

NOTE: For first iteration we do not re-embed; we assume documents are already indexed
when multi-doc mode is used. Later extensions can add retrieval logic using embeddings.
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
from distro import info
from jsonschema import Draft202012Validator
from app.services.workflows.validator import validate_output
from app.services.job_tracker import JobProgressTracker  # Reuse for progress
from app.utils.logging import logger
from app.config import settings
from app.db_models_workflows import WorkflowRun, Workflow
from jinja2 import Environment, StrictUndefined
from app.db_models_chat import DocumentChunk, CollectionDocument
from sqlalchemy import text as sql_text, select
from app.services.embeddings import get_embedding_provider
from app.utils.costs import compute_llm_cost
from app.services.artifacts import persist_artifact
from app.services.workflows.normalization import normalize_workflow_output
from app.utils.metrics import (
    WORKFLOW_RUNS_COMPLETED,
    WORKFLOW_RUNS_FAILED,
    WORKFLOW_RUNS_PARTIAL,
    WORKFLOW_LATENCY_SECONDS,
)
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
    return next(get_db())


def _llm():
    return LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.cheap_llm_model,
        max_tokens=settings.cheap_llm_max_tokens,
        max_input_chars=settings.llm_max_input_chars,
        timeout_seconds=settings.cheap_llm_timeout_seconds,
    )


@shared_task(bind=True)
def prepare_context_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble context for workflow run.

    For single-doc: load all chunks and optionally summarize.
    For multi-doc: lightweight retrieval placeholder (top N chunks per doc).
    """
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

        # SINGLE DOC PATH
        if run.mode == "single_doc" and doc_ids:
            doc_id = doc_ids[0]
            chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).order_by(DocumentChunk.chunk_index.asc()).all()
            # Basic summarization pass (cheap model) if large
            text_total = sum(len(c.text) for c in chunks)
            if text_total > 120_000:  # heuristic threshold
                llm_client = _llm()
                # Summarize first N narrative chunks (simple heuristic)
                narrative_chunks = [c for c in chunks if not c.is_tabular][:50]
                batch = [{"page": c.page_number, "text": c.text[:2000]} for c in narrative_chunks]
                summaries = asyncio.run(llm_client.summarize_chunks_batch(batch)) if batch else []
                context_sections.append("=== SUMMARIES ===")
                for s in summaries:
                    context_sections.append(s)
            # Always include tables & some narrative
            context_sections.append("=== CONTENT ===")
            for c in chunks:
                prefix = f"[Page {c.page_number}]"
                snippet = c.text
                context_sections.append(f"{prefix}\n{snippet}\n")
        else:
            # ---------------- Multi-Doc Retrieval Upgrade ----------------
            # Strategy: For each semantic section intent, run vector search queries across all selected documents.
            # Fall back to simple sampling if any errors occur.
            try:
                # Define retrieval sections (generic). Could be specialized per workflow later.
                sections_spec = [
                    {
                        "key": "executive",
                        "title": "EXECUTIVE OVERVIEW",
                        "queries": ["investment highlights", "key strengths", "business overview"],
                        "prefer_tables": False,
                    },
                    {
                        "key": "market",
                        "title": "MARKET & COMPETITION",
                        "queries": ["market size", "competitive landscape", "growth drivers", "competition"],
                        "prefer_tables": False,
                    },
                    {
                        "key": "financial",
                        "title": "FINANCIAL HIGHLIGHTS",
                        "queries": ["revenue growth", "ebitda margin", "financial performance", "profitability"],
                        "prefer_tables": True,
                    },
                    {
                        "key": "risks",
                        "title": "RISKS",
                        "queries": ["risk factors", "customer concentration", "regulatory risk", "operational risk"],
                        "prefer_tables": False,
                    },
                    {
                        "key": "actions",
                        "title": "RECOMMENDED ACTIONS",
                        "queries": ["recommended actions", "follow-up diligence", "next steps"],
                        "prefer_tables": False,
                    },
                ]

                embed_provider = get_embedding_provider()
                # Map doc id to short index used in citation labels
                doc_index_map = {doc_id: i + 1 for i, doc_id in enumerate(doc_ids)}

                # Helper: run a vector search for a single query string
                def vector_search(query: str, k: int = 8):
                    """Run a parameterized vector search using SQLAlchemy and pgvector.

                    Uses DocumentChunk.embedding.cosine_distance(query_vector) to build a safe
                    expression, and binds the list of document ids with an IN() clause using
                    SQLAlchemy's parameterization (DocumentChunk.document_id.in_(doc_ids)).

                    This avoids building SQL by string concatenation and prevents driver
                    binding errors when passing Python lists to the DB.
                    """
                    q_emb = embed_provider.embed_text(query)

                    # Use a short-lived DB session to isolate errors from the main task session
                    tmp_db = next(get_db())
                    try:
                        # Build a labelled distance expression so we can order by it safely
                        distance_expr = (DocumentChunk.embedding.cosine_distance(q_emb)).label("distance")

                        stmt = select(
                            DocumentChunk.id,
                            DocumentChunk.document_id,
                            DocumentChunk.page_number,
                            DocumentChunk.chunk_index,
                            DocumentChunk.text,
                            DocumentChunk.is_tabular,
                            distance_expr,
                        )

                        # Restrict to selected documents if provided (parameterized)
                        if doc_ids:
                            stmt = stmt.where(DocumentChunk.document_id.in_(doc_ids))

                        # Order by the computed distance (lower is better) and limit
                        stmt = stmt.order_by(distance_expr).limit(k)

                        rows = tmp_db.execute(stmt).fetchall()
                        return rows
                    finally:
                        try:
                            tmp_db.close()
                        except Exception:
                            pass

                MAX_CHARS_PER_CHUNK = 800
                TOTAL_UNIQUE_PER_SECTION = 20
                DIVERSITY_DOC_CAP_RATIO = 0.5  # max 50% from one doc per section

                for spec in sections_spec:
                    section_chunks = {}
                    # Collect candidate rows from all queries
                    for q in spec["queries"]:
                        try:
                            for r in vector_search(q):
                                if r.id in section_chunks:
                                    # Keep best (lowest distance)
                                    if r.distance < section_chunks[r.id]["distance"]:
                                        section_chunks[r.id]["distance"] = r.distance
                                else:
                                    section_chunks[r.id] = {
                                        "document_id": r.document_id,
                                        "page_number": r.page_number,
                                        "text": r.text,
                                        "is_tabular": r.is_tabular,
                                        "distance": r.distance,
                                    }
                        except Exception as inner_err:
                            # Rollback session to clear any aborted transaction caused by the failed vector query
                            try:
                                db.rollback()
                            except Exception:
                                pass
                            logger.warning("Vector search failed for query", extra={"query": q, "error": str(inner_err)})
                            continue

                    if not section_chunks:
                        continue

                    # Re-rank with bonuses / penalties
                    ranked = []
                    for cid, meta in section_chunks.items():
                        score = meta["distance"]  # lower is better
                        if spec.get("prefer_tables") and meta.get("is_tabular"):
                            score *= 0.9  # 10% bonus
                        ranked.append((cid, score, meta))
                    ranked.sort(key=lambda x: x[1])

                    # Diversity filtering
                    max_per_doc = max(1, int(TOTAL_UNIQUE_PER_SECTION * DIVERSITY_DOC_CAP_RATIO))
                    doc_counts = {}
                    final_selection = []
                    for cid, score, meta in ranked:
                        d = meta["document_id"]
                        doc_counts.setdefault(d, 0)
                        if doc_counts[d] >= max_per_doc:
                            continue
                        final_selection.append((cid, score, meta))
                        doc_counts[d] += 1
                        if len(final_selection) >= TOTAL_UNIQUE_PER_SECTION:
                            break

                    if not final_selection:
                        continue

                    context_sections.append(f"=== SECTION: {spec['title']} ===")
                    for cid, score, meta in final_selection:
                        d_index = doc_index_map.get(meta["document_id"], 0)
                        citation = f"[D{d_index}:p{meta['page_number']}]"
                        snippet = (meta["text"] or "")[:MAX_CHARS_PER_CHUNK].replace("\n", " ")
                        context_sections.append(f"{citation} {snippet}")

            except Exception as retrieval_err:
                # If any DB error occurred during retrieval, rollback to clear transaction before fallback queries
                try:
                    db.rollback()
                except Exception:
                    pass
                logger.error("Retrieval upgrade failed, falling back to sampling", extra={"error": str(retrieval_err)})
                for idx, doc_id in enumerate(doc_ids):
                    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).order_by(DocumentChunk.chunk_index.asc()).limit(30).all()
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

        # Handle both old data (JSON strings) and new data (Python objects)
        variables_raw = run.variables
        if isinstance(variables_raw, str):
            variables = json.loads(variables_raw or "{}")
        else:
            variables = variables_raw or {}

        # Check if user provided custom prompt (from UI)
        custom_prompt = payload.get("custom_prompt")

        if custom_prompt and workflow.user_prompt_template:
            # Dual-prompt architecture: combine user's custom prompt with system prompt
            # Import the template module to access the prompt_generator function
            try:
                if workflow.name == "Investment Memo":
                    from app.services.workflows.templates.investment_memo import get_investment_memo_prompt
                    rendered_template = get_investment_memo_prompt(variables, custom_prompt=custom_prompt)
                    logger.info("Using dual-prompt architecture with custom user prompt", extra={
                        "run_id": run_id,
                        "workflow_name": workflow.name,
                        "custom_prompt_length": len(custom_prompt)
                    })
                else:
                    # Fallback for templates without prompt_generator
                    rendered_template = custom_prompt
                    logger.warning("Workflow has user_prompt_template but no prompt_generator implementation", extra={
                        "run_id": run_id,
                        "workflow_name": workflow.name
                    })
            except Exception as e:
                logger.error("Failed to generate prompt using prompt_generator", extra={
                    "run_id": run_id,
                    "error": str(e)
                })
                repo.update_run_status(run_id, status="failed", error_message=f"Prompt generation error: {e}")
                tracker.mark_error(error_stage="generating", error_message=str(e), error_type="prompt_generation_error", is_retryable=False)
                return {"status": "failed", "error": "prompt_generation_failed", **payload}
        elif custom_prompt:
            # Legacy: Use user-edited prompt directly (for templates without dual-prompt support)
            rendered_template = custom_prompt
            logger.info("Using custom user-edited prompt (legacy mode)", extra={"run_id": run_id, "prompt_length": len(custom_prompt)})
        else:
            # No custom prompt: Use default template rendering
            # Jinja2 environment with strict undefined to surface missing vars early
            env = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
            try:
                # For dual-prompt templates, use the system prompt; otherwise use prompt_template
                template_str = workflow.prompt_template
                # Ensure variables is a dict
                if not isinstance(variables, dict):
                    variables = {}
                
                # Get safe defaults from workflow schema (single source of truth)
                safe_defaults = get_template_safe_defaults(workflow)
                
                # Merge defaults but keep explicit user-provided values
                for k, v in safe_defaults.items():
                    variables.setdefault(k, v)
                
                # Now render with StrictUndefined safely (keys are present)
                template = env.from_string(template_str)
                rendered_template = template.render(**variables)
            except Exception as e:
                # Fail fast if variable missing or template error
                repo.update_run_status(run_id, status="failed", error_message=f"Template render error: {e}")
                tracker.mark_error(error_stage="generating", error_message=str(e), error_type="template_error", is_retryable=False)
                return {"status": "failed", "error": "template_render_failed", **payload}

        # Prepend system instructions & citation policy
        prompt = (
            "SYSTEM:\nYou are producing a structured deliverable. Use ONLY bracketed citations that appear in the provided context preamble.\n"
            "Output MUST be valid JSON, no extra commentary.\n"
            + rendered_template
        )

        llm_client = _llm()
        model_name = settings.cheap_llm_model

        # ---------------- Citation & JSON Validation Loop ----------------
        allowed_citations = set(re.findall(r"\[D\d+:p\d+\]", combined_context))
        MAX_ATTEMPTS = min(2, settings.workflow_max_attempts - 1)  # Use config setting

        def compute_min_citations(allowed: set[str]) -> int:
            """Adaptive minimum citation requirement.

            Heuristics:
            - Base per doc: 2 citations per doc (multi-doc) else 3 minimum for single doc.
            - Clamp upper bound to 15 to avoid extreme requirements.
            - If allowed citations are sparse (< base), fall back to half of available (at least 1).
            - If context is large (>150k chars), bump requirement +2 for density.
            """
            # Handle both old data (JSON strings) and new data (Python objects)
            doc_ids_raw = run.document_ids
            if isinstance(doc_ids_raw, str):
                doc_ids_list = json.loads(doc_ids_raw or "[]")
            else:
                doc_ids_list = doc_ids_raw or []
            num_docs = len(doc_ids_list)
            context_len = len(combined_context)
            if num_docs <= 1:
                base = 3
            else:
                base = min(15, max(2, num_docs * 2))  # multi-doc scaling
            if context_len > 150_000:
                base += 2
            if len(allowed) < base:
                base = max(1, len(allowed) // 2 or (1 if len(allowed) > 0 else 0))
            return base or 1

        MIN_CITATIONS = compute_min_citations(allowed_citations)

        last_invalid_reason = ""
        final_json = None
        raw_response = None
        used_citations: List[str] = []
        invalid_citations: List[str] = []
        validation_errors: List[dict] = []  # Initialize validation_errors before loop
        last_parsed_candidate = None  # keep most recent parsed_candidate even if invalid
        
        citation_snippets = {}
        for line in combined_context.splitlines():
            found = re.findall(r"\[D\d+:p\d+\]", line)
            if not found:
                continue
            remainder = re.sub(r"\[D\d+:p\d+\]\s*", "", line).strip()
            for c in found:
                if c not in citation_snippets and remainder:
                    citation_snippets[c] = remainder[:500]

        for attempt in range(MAX_ATTEMPTS):
            # call LLM (wrap to avoid crash on network/timeout)
            try:
                llm_result = asyncio.run(
                    llm_client.extract_structured_data(
                        combined_context,
                        prompt if attempt == 0 else corrective_prompt
                    )
                )
            except Exception as call_err:
                logger.warning("LLM call error, will retry if attempts remain", extra={"run_id": run_id, "attempt": attempt, "error": str(call_err)})
                last_invalid_reason = f"LLM call failed: {call_err}"
                if attempt == MAX_ATTEMPTS - 1:
                    break
                # small backoff before retry
                time.sleep(min(2 ** attempt, 8))
                continue
            
            info = handle_llm_result(run_id, combined_context, llm_result)
            raw_response = info["raw_text"]
            parsed_candidate = info["parsed_candidate"]
            usage_meta = info["usage_meta"]
            used_citations = info["used_citations"]
            invalid_citations = info["invalid_citations"]
            json_ok = info.get("json_ok", False)
            json_parsed = info.get("json_parsed")  # may be None

            if isinstance(parsed_candidate, dict):
                last_parsed_candidate = parsed_candidate
            elif isinstance(json_parsed, dict):
                last_parsed_candidate = json_parsed
                
            citation_count = len(used_citations)

            # Decide parsed value precedence:
            # 1) If we successfully parsed JSON from raw LLM output (json_ok), use json_parsed
            # 2) Else if parsed_candidate provided by LLM client, use that
            # 3) Else None
            parsed = json_parsed if json_ok and isinstance(json_parsed, dict) else (parsed_candidate if isinstance(parsed_candidate, dict) else None)

            # Structural acceptance rule: JSON parsed AND no invalid citations
            structural_ok = parsed is not None and len(invalid_citations) == 0

            if structural_ok:
                final_json = parsed
                # Add citation warning if count is low (but don't fail)
                if citation_count < MIN_CITATIONS:
                    validation_errors.append({
                        "code": "citation_count_warning",
                        "message": f"Low citation count ({citation_count} < {MIN_CITATIONS} recommended)",
                        "severity": "warning"
                    })
                break

            problems = []
            if not parsed:
                problems.append(f"JSON invalid or not present (parsed_present={bool(parsed)})")
            # Citation count moved to warning above, only fail on invalid citations
            if invalid_citations:
                problems.append(f"Invalid citations not in context: {', '.join(invalid_citations[:10])}")
            last_invalid_reason = "; ".join(problems) or "Unknown validation failure"

            if attempt == MAX_ATTEMPTS - 1:
                break

            # Prepare corrective prompt for next iteration (lean, focused)
            corrective_prompt = (
                "SYSTEM CORRECTION:\nPrevious output had issues: " + last_invalid_reason + "\n"
                "Re-output STRICT valid JSON. Use ONLY citations from this allowed set: "
                + ", ".join(sorted(list(allowed_citations))[:60]) + "\n"
                f"Ensure at least {MIN_CITATIONS} citations (adaptive threshold) and remove any invalid ones. Do not add commentary outside JSON."\
            ) + "\n" + rendered_template

        schema_errors = []
        schema_applied = False
        if final_json and workflow.output_schema and workflow.output_format == "json":
            try:
                schema_obj = json.loads(workflow.output_schema)
                validator = Draft202012Validator(schema_obj)
                for err in sorted(validator.iter_errors(final_json), key=lambda e: e.path):
                    schema_errors.append({"code": "json_schema_violation", "path": list(err.path), "message": err.message})
                schema_applied = True
            except Exception as se:
                schema_errors.append({"code": "schema_processing_error", "message": str(se)})

        # Build validation_errors from last_invalid_reason only if we failed
        if last_invalid_reason and not final_json:
            parts = last_invalid_reason.split("; ")
            for p in parts:
                if p.startswith("JSON invalid"):
                    validation_errors.append({"code": "json_invalid", "message": p, "severity": "error"})
                # Citation count is now handled as warning above, not an error
                if p.startswith("Invalid citations"):
                    validation_errors.append({"code": "citation_invalid", "message": p, "severity": "error"})
        validation_errors.extend(schema_errors)

        validation_info = {
            "attempts": attempt + 1,
            "citation_count": len(used_citations),
            "invalid_citations": invalid_citations,
            "allowed_citations_sample": list(sorted(allowed_citations))[:40],
            "last_invalid_reason": last_invalid_reason,
            "finalized": final_json is not None,
            "schema_applied": schema_applied,
            "schema_error_count": len(schema_errors),
            "token_usage": usage_meta,
        }

        if not final_json:
            # ---- Partial Success Salvage ----
            salvage = None
            salvage_reason = None

            # Prefer last_parsed_candidate if available (even if citation / schema issues)
            if last_parsed_candidate:
                salvage = last_parsed_candidate
                salvage_reason = "used last parsed candidate despite validation failures"
            else:
                # Try regex extraction of first JSON object
                match = re.search(r"\{[\s\S]*\}", raw_response)
                if match:
                    try:
                        maybe = json.loads(match.group(0))
                        if isinstance(maybe, dict) and maybe:
                            salvage = maybe
                            salvage_reason = "extracted first JSON object substring"
                    except Exception:
                        pass

            # If salvage exists, mark run as partial instead of full fail
            if salvage:
                artifact = {
                    "raw": raw_response,
                    "partial_parsed": salvage,
                    "validation": validation_info,
                    "errors": validation_errors,
                    "partial": True,
                    "salvage_reason": salvage_reason,
                    "citation_snippets": citation_snippets,
                }
                artifact_ptr = persist_artifact(run_id, artifact)
                artifact_record = dict(artifact_ptr)
                artifact_record["summary"] = {
                    "finalized": False,
                    "partial": True,
                    "attempts": attempt + 1,
                    "citation_count": len(used_citations),
                    "invalid_citations_count": len(invalid_citations),
                    "schema_error_count": validation_info.get("schema_error_count", 0),
                    "model": model_name,
                    "format": workflow.output_format,
                }
                repo.update_run_status(
                    run_id,
                    status="failed",  # keep status failed for now; UI can treat failed+partial flag specially
                    artifact_json=artifact_record,
                    error_message=last_invalid_reason,
                    citation_invalid_count=len(invalid_citations),
                    attempts=attempt+1,
                    validation_errors_json=json.dumps(validation_errors),
                )
                WORKFLOW_RUNS_PARTIAL.inc()
                tracker.mark_error(error_stage="generating", error_message=last_invalid_reason, error_type="validation_error", is_retryable=False)
                return {"status": "partial_failed", "run_id": run_id, "job_id": job_id, "error": "validation_partial"}

            # No salvage possible -> hard fail
            artifact = {"raw": raw_response, "validation": validation_info, "errors": validation_errors, "partial": False}
            artifact_ptr = persist_artifact(run_id, artifact)
            artifact_record = dict(artifact_ptr)
            artifact_record["summary"] = {
                "finalized": False,
                "partial": False,
                "attempts": attempt + 1,
                "citation_count": len(used_citations),
                "invalid_citations_count": len(invalid_citations),
                "schema_error_count": validation_info.get("schema_error_count", 0),
                "model": model_name,
                "format": workflow.output_format,
            }
            repo.update_run_status(run_id, status="failed", artifact_json=artifact_record, error_message=last_invalid_reason, citation_invalid_count=len(invalid_citations), attempts=attempt+1, validation_errors_json=json.dumps(validation_errors))
            WORKFLOW_RUNS_FAILED.inc()
            tracker.mark_error(error_stage="generating", error_message=last_invalid_reason, error_type="validation_error", is_retryable=True)
            return {"status": "failed", "run_id": run_id, "job_id": job_id, "error": "validation_failed"}

        # ---- Normalize LLM Output (comprehensive normalization) ----
        logger.info("Normalizing LLM output before schema validation", extra={"run_id": run_id})
        # First apply simple normalization (existing function)
        final_json = normalize_llm_output(final_json, workflow.name)
        # Then apply comprehensive workflow-specific normalization
        currency = final_json.get("currency", "USD")
        final_json = normalize_workflow_output(final_json, workflow.name, currency=currency)

        # ---- Runtime Schema Validation (secondary pass via modular validator) ----
        secondary_validation = validate_output(workflow.name, final_json)
        if not secondary_validation.valid:
            logger.error("Secondary validation errors", extra={
                "run_id": run_id,
                "errors": [ {"code": e.code, "path": e.path, "message": e.message} for e in secondary_validation.errors ]
            })
            # Merge schema violations into validation_errors
            for ve in secondary_validation.errors:
                validation_errors.append({"code": ve.code, "message": ve.message, "path": ve.path})
            # Mark as partial if structural schema broken but JSON still parsed
            validation_info["secondary_schema_error_count"] = len(secondary_validation.errors)
            # Decide fail vs partial: keep completed if only warnings; if errors, downgrade to partial_failed
            if secondary_validation.errors:
                artifact = {
                    "raw": raw_response,
                    "parsed": final_json,
                    "validation": validation_info,
                    "errors": validation_errors,
                    "citation_snippets": citation_snippets,
                    "partial": True,
                    "secondary_schema_failed": True,
                }
                artifact_ptr = persist_artifact(run_id, artifact)
                artifact_record = dict(artifact_ptr)
                artifact_record["summary"] = {
                    "finalized": False,
                    "partial": True,
                    "attempts": attempt + 1,
                    "citation_count": len(used_citations),
                    "invalid_citations_count": len(invalid_citations),
                    "schema_error_count": validation_info.get("schema_error_count", 0),
                    "secondary_schema_error_count": len(secondary_validation.errors),
                    "model": model_name,
                    "format": workflow.output_format,
                }
                error_msg = f"Secondary schema validation failed with {len(secondary_validation.errors)} error(s)"
                repo.update_run_status(
                    run_id,
                    status="failed",
                    artifact_json=artifact_record,
                    error_message=error_msg,
                    latency_ms=int((time.time()-start)*1000),
                    citations_count=len(used_citations),
                    citation_invalid_count=len(invalid_citations),
                    attempts=attempt+1,
                    validation_errors_json=json.dumps(validation_errors),
                )
                WORKFLOW_RUNS_PARTIAL.inc()
                tracker.mark_error(error_stage="generating", error_message=error_msg, error_type="schema_error", is_retryable=False)
                return {"status": "partial_failed", "run_id": run_id, "job_id": job_id, "error": "secondary_schema_failed"}
        artifact = {"raw": raw_response, "parsed": final_json, "validation": validation_info, "errors": validation_errors, "citation_snippets": citation_snippets}

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

        artifact_ptr = persist_artifact(run_id, artifact)
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
            cost_usd=cost_usd
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
