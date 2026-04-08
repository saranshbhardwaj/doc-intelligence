"""LLM service for template filling: field detection, auto-mapping, and data extraction.

Uses Anthropic's Structured Outputs feature to GUARANTEE valid JSON responses.
"""

import asyncio
import hashlib
import json
import re
import time

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from anthropic import Anthropic

from app.config import settings
from app.core.redis_client import get_redis_client_for_cache
from app.utils.logging import logger
from app.utils.token_utils import count_tokens
from app.utils.metrics import LLM_TOKEN_USAGE, LLM_CACHE_HITS, LLM_CACHE_MISSES, LLM_REQUESTS_TOTAL, LLM_COST_USD
from app.utils.costs import compute_llm_cost
from app.verticals.real_estate.template_filling.prompts import (
    get_prompt_set,
    SchemaTableExtractionResult,
)

TABLE_HEADER_CACHE_TTL_SECONDS = 60 * 60 * 24
TABLE_HEADER_MIN_COVERAGE = 0.5
TABLE_HEADER_STRONG_COVERAGE = 0.7
TABLE_HEADER_MATCH_THRESHOLD = 0.82
TABLE_HEADER_EQUIVALENTS = """Table header equivalences (case-insensitive):
- Type, Unit Type, Unit, Floor Plan
- # Units, Units, Unit Count, Count
- Sqft, Sq Ft, Sq.Ft., Square Feet, SF
- Sq.Ft./Unit, SF/Unit, Size, Area
- Rent/Unit, Rent, Monthly Rent, Asking Rent
- Rent/Sq Ft, Rent/Sq.Ft., Rent per Sq Ft, $/SF
"""


def _normalize_header(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    t = t.replace("sq. ft.", "sqft").replace("sq.ft.", "sqft").replace("sq ft", "sqft")
    t = t.replace("square feet", "sqft").replace("sq. ft", "sqft")
    t = t.replace("per unit", "per_unit").replace("per sq ft", "per_sqft")
    t = t.replace("rent/sq. ft.", "rent_per_sqft").replace("rent/sq ft", "rent_per_sqft")
    t = t.replace("#", "number ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokenize_header(text: str) -> List[str]:
    return [t for t in _normalize_header(text).split(" ") if t]


def _similarity_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    na = _normalize_header(a)
    nb = _normalize_header(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta = set(_tokenize_header(na))
    tb = set(_tokenize_header(nb))
    if not ta or not tb:
        return ratio
    jaccard = len(ta & tb) / len(ta | tb)
    return max(ratio, jaccard)


def _build_table_signature(headers: List[str], row_count: int, col_count: int) -> str:
    normalized_headers = [_normalize_header(h or "") for h in headers]
    raw_sig = "|".join(normalized_headers) + f":{row_count}:{col_count}"
    return hashlib.sha1(raw_sig.encode("utf-8")).hexdigest()[:16]


def _resolve_column_map(
    schema_columns: List[Dict[str, Any]],
    pdf_headers: List[str],
) -> Tuple[Dict[str, str], float]:
    candidates: List[Tuple[str, str, float]] = []
    for col in schema_columns:
        excel_col = col.get("excel_column")
        if not excel_col:
            continue
        aliases = [col.get("header") or ""] + list(col.get("pdf_aliases") or [])
        best_header = None
        best_score = 0.0
        for header in pdf_headers:
            score = 0.0
            for alias in aliases:
                if not alias:
                    continue
                score = max(score, _similarity_score(alias, header))
            if score > best_score:
                best_score = score
                best_header = header
        if best_header and best_score >= TABLE_HEADER_MATCH_THRESHOLD:
            candidates.append((excel_col, best_header, best_score))

    # Resolve duplicates by best score
    column_map: Dict[str, str] = {}
    used_headers: set[str] = set()
    for excel_col, header, score in sorted(candidates, key=lambda x: x[2], reverse=True):
        if header in used_headers:
            continue
        column_map[excel_col] = header
        used_headers.add(header)

    total_cols = len([c for c in schema_columns if c.get("excel_column")])
    coverage = len(column_map) / max(total_cols, 1)
    return column_map, coverage

# ============================================================================
# LLM Service
# ============================================================================

class TemplateFillLLMService:
    """LLM service for intelligent template filling operations with guaranteed valid JSON."""

    def __init__(
        self,
        prompt_version: str | None = None,
        capture_io_log: bool = False,
        fill_run_id: str | None = None,
    ):
        """Initialize LLM service with Anthropic client and versioned prompts.

        Args:
            prompt_version: Prompt set version to use (defaults to settings.re_template_prompt_version).
            capture_io_log: When True, persist each LLM call's prompt/response to llm_io_logs.
                            Off by default — never enable in production unless debugging/eval export.
            fill_run_id: Fill run ID used as source_id in llm_io_logs (required when capture_io_log=True).
        """
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.synthesis_llm_model
        self.max_tokens = settings.synthesis_llm_max_tokens
        self.prompts = get_prompt_set(prompt_version)
        self.capture_io_log = capture_io_log
        self.fill_run_id = fill_run_id or "unknown"
        if capture_io_log:
            from app.repositories.io_log_repository import IOLogRepository
            self._io_log_repo = IOLogRepository()
        else:
            self._io_log_repo = None

    def _record_llm_metrics(
        self,
        input_tokens: int | None,
        output_tokens: int | None,
        cache_read_tokens: int | None,
        cache_write_tokens: int | None,
    ) -> None:
        """Record LLM metrics for template fill extraction."""
        try:
            LLM_REQUESTS_TOTAL.labels(model=self.model, operation_type="extraction").inc()
            if input_tokens:
                LLM_TOKEN_USAGE.labels(model=self.model, token_type="input", operation_type="extraction").inc(input_tokens)
            if output_tokens:
                LLM_TOKEN_USAGE.labels(model=self.model, token_type="output", operation_type="extraction").inc(output_tokens)
            if cache_read_tokens:
                LLM_TOKEN_USAGE.labels(model=self.model, token_type="cache_read", operation_type="extraction").inc(cache_read_tokens)
                LLM_CACHE_HITS.labels(operation_type="extraction").inc()
            else:
                LLM_CACHE_MISSES.labels(operation_type="extraction").inc()
            if cache_write_tokens:
                LLM_TOKEN_USAGE.labels(model=self.model, token_type="cache_write", operation_type="extraction").inc(cache_write_tokens)
            if input_tokens and output_tokens:
                cost = compute_llm_cost(self.model, input_tokens, output_tokens)
                if cost:
                    LLM_COST_USD.labels(model=self.model, operation_type="extraction").inc(cost)
        except Exception as e:
            logger.warning(f"Failed to record template fill LLM metrics: {e}")

    async def detect_pdf_fields(
        self,
        chunks_with_metadata: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Detect all fillable fields from a PDF document with citation support.

        Uses Anthropic's Structured Outputs to GUARANTEE valid JSON response.

        Args:
            chunks_with_metadata: List of document chunks with metadata

        Returns:
            {
                "fields": [...],
                "total_fields": 45,
                "categories": [...]
            }
        """
        logger.info("Detecting PDF fields using LLM with structured outputs (guaranteed valid JSON)")

        context = self._format_chunks_with_citations(chunks_with_metadata)
        pair = self.prompts.build_detect_fields(context)

        t0 = time.time()
        try:
            message = await asyncio.to_thread(
                self.client.messages.parse,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.0,
                timeout=settings.synthesis_llm_timeout_seconds,
                messages=[{"role": "user", "content": pair.user_message}],
                output_format=pair.response_model,
            )

            parsed_output = message.parsed_output
            result = parsed_output.model_dump()

            logger.info(f"✅ Detected {len(result.get('fields', []))} fields from PDF (structured output)")

            for idx, field in enumerate(result.get("fields", []), start=1):
                if "id" not in field:
                    field["id"] = f"f{idx}"

            usage = message.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

            # Record metrics
            self._record_llm_metrics(input_tokens, output_tokens, cache_read, cache_creation)

            if self.capture_io_log and self._io_log_repo:
                self._io_log_repo.save_io_log(
                    source_type="template_fill",
                    source_id=self.fill_run_id,
                    stage="detect_fields",
                    prompt_version=self.prompts.version,
                    user_message=pair.user_message,
                    output=result,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_creation_tokens=cache_creation,
                    cache_read_tokens=cache_read,
                    duration_ms=int((time.time() - t0) * 1000),
                )

            return result

        except Exception as e:
            logger.error(f"Error detecting PDF fields: {e}", exc_info=True)
            raise

    async def extract_schema_field_values(
        self,
        unmapped_fields: List[Dict[str, Any]],
        pdf_fields: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Stage 2: Targeted extraction of specific YAML schema fields from Azure DI output.

        Instead of asking the LLM "which cells in these sheets match these PDF fields"
        (generic 6-batch approach), we ask "for each of these 63 named schema fields,
        what value does the PDF contain?" — a much more focused and accurate prompt.

        Args:
            unmapped_fields: Schema field defs that weren't matched in Stage 1 (alias match).
                             Each dict has: id, sheet, value_cell, label_cell, data_type, pdf_aliases.
            pdf_fields: All Azure DI key-value fields extracted from the PDF.

        Returns:
            Dict of {field_id: {"value": str, "confidence": float, "citations": List[str]}}
            Only fields actually found in the PDF are included (no null entries).
        """
        if not unmapped_fields or not pdf_fields:
            return {}

        logger.info(
            f"🎯 Stage 2 targeted extraction: {len(unmapped_fields)} unmapped schema fields "
            f"from {len(pdf_fields)} Azure DI fields"
        )

        # Split into KV, table_block, and narrative_block fields for LLM context.
        # Per-column table fields (source="table") are excluded — they are redundant
        # because table_block fields already contain the full table with all rows.
        kv_fields = [f for f in pdf_fields if f.get("source") == "key_value_pairs"]
        table_block_fields = [f for f in pdf_fields if f.get("source") == "table_block"]
        narrative_block_fields = [f for f in pdf_fields if f.get("source") == "narrative_block"]
        # Fall back to all fields if no table_block fields exist (backward compat)
        fields_for_llm = kv_fields + table_block_fields + narrative_block_fields if table_block_fields else pdf_fields
        stripped_pdf_fields = [self._strip_pdf_field(f) for f in fields_for_llm]
        pdf_fields_json = json.dumps(stripped_pdf_fields, separators=(",", ":"), ensure_ascii=False)

        logger.info(
            f"🎯 Stage 2 LLM context: {len(kv_fields)} KV fields + {len(table_block_fields)} table blocks + {len(narrative_block_fields)} narrative blocks"
        )

        # Build prompt pair from versioned prompt set
        pair = self.prompts.build_extract_schema_fields(pdf_fields_json, unmapped_fields)
        system_prompt = pair.system_prompt
        user_message = pair.user_message

        system_arg = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        t0 = time.time()
        message = await asyncio.to_thread(
            self.client.messages.parse,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.0,
            timeout=settings.synthesis_llm_timeout_seconds,
            system=system_arg,
            messages=[{"role": "user", "content": user_message}],
            output_format=pair.response_model,
        )
        duration_ms = int((time.time() - t0) * 1000)

        # Log token usage
        usage = getattr(message, "usage", None)
        cache_creation = cache_read = input_tokens = output_tokens = 0
        if usage is not None:
            cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            logger.info(
                f"🎯 Stage 2 tokens: input={input_tokens:,}, output={output_tokens:,}, "
                f"cache_creation={cache_creation:,}, cache_read={cache_read:,}"
            )

        # Record metrics
        self._record_llm_metrics(input_tokens, output_tokens, cache_read, cache_creation)

        # Build {field_id: {value, confidence, citations}} — only for found fields
        parsed = message.parsed_output
        result_by_field: Dict[str, Any] = {}
        for item in parsed.results:
            if item.value:
                result_by_field[item.field_id] = {
                    "value": item.value,
                    "confidence": item.confidence,
                    "citations": item.citations,
                    "reasoning": item.reasoning,
                }

        found_count = len(result_by_field)
        not_found_count = len(unmapped_fields) - found_count
        logger.info(
            f"✅ Stage 2 complete: {found_count}/{len(unmapped_fields)} fields found "
            f"({not_found_count} not present in this PDF)"
        )

        if self.capture_io_log and self._io_log_repo:
            self._io_log_repo.save_io_log(
                source_type="template_fill",
                source_id=self.fill_run_id,
                stage="extract_schema_fields",
                prompt_version=self.prompts.version,
                system_prompt=system_prompt,
                user_message=user_message,
                output=parsed.model_dump() if parsed else None,
                metadata={
                    "unmapped_fields": [
                        {"id": f.get("id"), "data_type": f.get("data_type"), "pdf_aliases": f.get("pdf_aliases", [])}
                        for f in unmapped_fields
                    ],
                },
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_tokens=cache_creation,
                cache_read_tokens=cache_read,
                duration_ms=duration_ms,
            )

        return result_by_field

    # async def extract_schema_field_values(
    #     self,
    #     unmapped_fields: List[Dict[str, Any]],
    #     pdf_fields: List[Dict[str, Any]],
    # ) -> Dict[str, Any]:
    #     if not unmapped_fields or not pdf_fields:
    #         return {}

    #     logger.info(
    #         f"🎯 Stage 2 targeted extraction: {len(unmapped_fields)} unmapped schema fields "
    #         f"from {len(pdf_fields)} Azure DI fields"
    #     )

    #     kv_fields = [f for f in pdf_fields if f.get("source") == "key_value_pairs"]
    #     table_block_fields = [f for f in pdf_fields if f.get("source") == "table_block"]
    #     narrative_block_fields = [f for f in pdf_fields if f.get("source") == "narrative_block"]
    #     fields_for_llm = kv_fields + table_block_fields + narrative_block_fields if table_block_fields else pdf_fields
    #     stripped_pdf_fields = [self._strip_pdf_field(f) for f in fields_for_llm]
    #     pdf_fields_json = json.dumps(stripped_pdf_fields, separators=(",", ":"), ensure_ascii=False)

    #     logger.info(
    #         f"🎯 Stage 2 LLM context: {len(kv_fields)} KV fields + "
    #         f"{len(table_block_fields)} table blocks + {len(narrative_block_fields)} narrative blocks"
    #     )

    #     system_prompt = f"""You are extracting values from a real estate PDF for specific named schema fields.

    # Below is the complete list of key-value pairs, full tables, and market context (narratives) extracted by Azure Document Intelligence:
    # ```json
    # {pdf_fields_json}
    # ```

    # For each requested schema field, find its value from the Azure DI data above.
    # Match by the field's aliases and semantic meaning. For example:
    # - A field with aliases ["City", "Location City"] might appear as "City:", "Location:", "Property City", etc.
    # - A field with aliases ["Asking Price", "Purchase Price"] might appear as "List Price", "Sale Price", etc.

    # Be aggressive in matching — if a value is semantically equivalent to an alias, extract it.
    # Return null only if the value genuinely cannot be found anywhere in the PDF data."""

    #     fields_for_request = [
    #         {
    #             "id": f["id"],
    #             "aliases": f.get("pdf_aliases", []),
    #             "data_type": f.get("data_type", "text"),
    #         }
    #         for f in unmapped_fields
    #     ]

    #     user_message = (
    #         f"Find values for these {len(fields_for_request)} schema fields from the Azure DI data "
    #         f"in the system prompt.\n\n"
    #         f"Fields to extract:\n```json\n"
    #         f"{json.dumps(fields_for_request, indent=2)}\n```\n\n"
    #         f"IMPORTANT - Data Type Validation Rules:\n"
    #         f"- currency: Must be numeric with $ sign (e.g., '$450,000'). Return null for non-numeric text.\n"
    #         f"- number: Must be numeric (e.g., '100', '3.14'). Return null for non-numeric text.\n"
    #         f"- percentage: Must include % (e.g., '65%', '8.11%'). Return null if not a percentage.\n"
    #         f"- date: Must be a date (e.g., '2026-03-10', 'March 10, 2026'). Return null for non-dates.\n"
    #         f"- text: Any text value is acceptable.\n\n"
    #         f"CRITICAL: You MUST attempt to find a value for every single field. "
    #         f"Do not skip fields. If a field has multiple possible aliases, try all of them. "
    #         f"Only return null if the value is truly absent from the PDF data.\n\n"
    #         f"Return ONLY a JSON object matching this exact structure, no markdown:\n"
    #         "{\n"
    #         '  "results": [\n'
    #         "    {\n"
    #         '      "field_id": "field_id_here",\n'
    #         '      "value": "extracted value or null",\n'
    #         '      "confidence": 0.95,\n'
    #         '      "citations": ["[S1:p3]"],\n'
    #         '      "reasoning": "Found as currency: $2,500,000 in KV pair Listing Price"\n'
    #         "    }\n"
    #         "  ],\n"
    #         f'  "total_found": 10,\n'
    #         f'  "total_not_found": 2\n'
    #         "}\n"
    #     )

    #     system_arg = [
    #         {
    #             "type": "text",
    #             "text": system_prompt,
    #             "cache_control": {"type": "ephemeral"},
    #         }
    #     ]

    #     response = await asyncio.to_thread(
    #         self.client.messages.create,
    #         model=self.model,
    #         max_tokens=self.max_tokens,
    #         temperature=0.0,
    #         timeout=settings.synthesis_llm_timeout_seconds,
    #         system=system_arg,
    #         messages=[{"role": "user", "content": user_message}],
    #     )

    #     # Log token usage
    #     usage = getattr(response, "usage", None)
    #     if usage is not None:
    #         cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    #         cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    #         input_tokens = getattr(usage, "input_tokens", 0) or 0
    #         output_tokens = getattr(usage, "output_tokens", 0) or 0
    #         logger.info(
    #             f"🎯 Stage 2 tokens: input={input_tokens:,}, output={output_tokens:,}, "
    #             f"cache_creation={cache_creation:,}, cache_read={cache_read:,}"
    #         )

    #     raw_text = response.content[0].text.strip()
    #     if raw_text.startswith("```"):
    #         raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
    #         raw_text = re.sub(r"\n?```$", "", raw_text)

    #     try:
    #         raw_result = json.loads(raw_text)
    #         parsed = SchemaFieldExtractionResult(**raw_result)
    #     except (json.JSONDecodeError, ValidationError) as e:
    #         logger.error(f"Failed to parse field extraction response: {e}\nRaw: {raw_text[:500]}")
    #         return {}

    #     result_by_field: Dict[str, Any] = {}
    #     for item in parsed.results:
    #         if item.value:
    #             result_by_field[item.field_id] = {
    #                 "value": item.value,
    #                 "confidence": item.confidence,
    #                 "citations": item.citations,
    #                 "reasoning": item.reasoning,
    #             }

    #     found_count = len(result_by_field)
    #     not_found_count = len(unmapped_fields) - found_count
    #     logger.info(
    #         f"✅ Stage 2 complete: {found_count}/{len(unmapped_fields)} fields found "
    #         f"({not_found_count} not present in this PDF)"
    #     )

    #     return result_by_field

    async def extract_schema_table_values(
        self,
        schema_tables: List[Dict[str, Any]],
        pdf_fields: List[Dict[str, Any]],
        table_row_labels: Optional[Dict[str, Any]] = None,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        NOT GETTING USED IN CURRENT IMPLEMENTATION
        Stage 2: Targeted extraction of YAML schema table values from Azure DI output.

        Args:
            schema_tables: List of schema table definitions from YAML.
            pdf_fields: All Azure DI key-value fields extracted from the PDF.
            table_row_labels: Optional mapping of table_id -> {row_labels: [...], start_row, end_row}

        Returns:
            Dict: {table_id: {"rows": [...]}}
        """
        if not schema_tables or not pdf_fields:
            return {}

        logger.info(
            f"🎯 Stage 2 targeted table extraction: {len(schema_tables)} schema tables "
            f"from {len(pdf_fields)} Azure DI fields"
        )

        kv_fields = [f for f in pdf_fields if f.get("source") == "key_value_pairs"]
        table_block_fields = [f for f in pdf_fields if f.get("source") == "table_block"]
        narrative_block_fields = [f for f in pdf_fields if f.get("source") == "narrative_block"]
        fields_for_llm = kv_fields + table_block_fields + narrative_block_fields if table_block_fields else pdf_fields

        if not table_block_fields:
            logger.warning("Stage 2 table extraction skipped: no table_block fields found in pdf_fields")
            return {}

        stripped_pdf_fields = [self._strip_pdf_field(f) for f in fields_for_llm]
        pdf_fields_json = json.dumps(stripped_pdf_fields, separators=(",", ":"), ensure_ascii=False)

        table_candidates = []
        for table_field in table_block_fields:
            columns = table_field.get("table_columns") or []
            if not columns:
                continue
            table_candidates.append({
                "id": table_field.get("id"),
                "name": table_field.get("table_name") or table_field.get("name") or "Table",
                "columns": columns,
                "rows": table_field.get("table_rows") or [],
                "page_number": table_field.get("page_number"),
            })

        if not table_candidates:
            logger.warning("Stage 2 table extraction skipped: no usable table candidates found")
            return {}

        table_requests = []
        table_row_labels = table_row_labels or {}
        redis_client = None
        if document_id:
            try:
                redis_client = get_redis_client_for_cache()
            except Exception as e:
                logger.warning(f"Redis cache unavailable for table header mapping: {e}")

        for table in schema_tables:
            table_id = table.get("id")
            if not table_id:
                continue
            start_row = table.get("data_start_row")
            end_row = table.get("data_end_row", start_row)
            row_labels = table_row_labels.get(table_id, {}).get("row_labels", [])
            columns = [
                {
                    "excel_column": c.get("excel_column"),
                    "header": c.get("header"),
                    "data_type": c.get("data_type", "text"),
                    "pdf_aliases": c.get("pdf_aliases", []),
                }
                for c in table.get("columns", [])
            ]

            best_candidate = None
            best_column_map: Dict[str, str] = {}
            best_coverage = 0.0
            best_sig = None

            for candidate in table_candidates:
                headers = candidate.get("columns", [])
                row_count = len(candidate.get("rows", []))
                col_count = len(headers)
                table_sig = _build_table_signature(headers, row_count, col_count)

                cached_map = None
                cached_coverage = 0.0
                if redis_client is not None:
                    cache_key = f"template_fill:table_header_map:{document_id}:{table_id}:{table_sig}"
                    try:
                        cached_raw = redis_client.get(cache_key)
                        if cached_raw:
                            cached_text = cached_raw.decode("utf-8") if isinstance(cached_raw, bytes) else cached_raw
                            cached_payload = json.loads(cached_text)
                            cached_map = cached_payload.get("column_map", {})
                            cached_coverage = float(cached_payload.get("coverage") or 0.0)
                    except Exception as e:
                        logger.debug(f"Failed to read table header cache: {e}")

                if cached_map:
                    column_map = cached_map
                    coverage = cached_coverage or (len(column_map) / max(len(columns), 1))
                    logger.info(
                        f"✓ Table header cache hit: table_id={table_id} coverage={coverage:.2f}"
                    )
                else:
                    column_map, coverage = _resolve_column_map(columns, headers)
                    logger.info(
                        f"Table header match candidate: table_id={table_id} "
                        f"candidate='{candidate.get('name')}' "
                        f"coverage={coverage:.2f} "
                        f"matched_cols={len(column_map)}/{max(len(columns), 1)}"
                    )
                    if redis_client is not None and coverage >= TABLE_HEADER_STRONG_COVERAGE:
                        cache_key = f"template_fill:table_header_map:{document_id}:{table_id}:{table_sig}"
                        cache_payload = {
                            "column_map": column_map,
                            "coverage": coverage,
                            "headers": headers,
                            "table_name": candidate.get("name"),
                        }
                        try:
                            redis_client.setex(
                                cache_key,
                                TABLE_HEADER_CACHE_TTL_SECONDS,
                                json.dumps(cache_payload),
                            )
                        except Exception as e:
                            logger.debug(f"Failed to write table header cache: {e}")

                if coverage > best_coverage:
                    best_candidate = candidate
                    best_column_map = column_map
                    best_coverage = coverage
                    best_sig = table_sig

            if best_candidate is None:
                logger.warning(f"No table candidate found for schema table {table_id}")
                continue
            if best_coverage < TABLE_HEADER_MIN_COVERAGE:
                logger.info(
                    f"Low header coverage for table {table_id}: {best_coverage:.2f} "
                    f"(LLM will infer remaining columns)"
                )
            logger.info(
                f"Selected table candidate for {table_id}: "
                f"'{best_candidate.get('name')}' "
                f"coverage={best_coverage:.2f} "
                f"column_map={best_column_map}"
            )

            table_requests.append({
                "table_id": table_id,
                "sheet": table.get("sheet"),
                "data_start_row": start_row,
                "data_end_row": end_row,
                "row_identifier_column": table.get("row_identifier_column"),
                "row_labels": row_labels,
                "columns": columns,
                "column_map": best_column_map,
                "column_map_coverage": round(best_coverage, 3),
                "preferred_table": {
                    "table_name": best_candidate.get("name"),
                    "table_columns": best_candidate.get("columns", []),
                    "page_number": best_candidate.get("page_number"),
                    "table_signature": best_sig,
                },
            })

        if not table_requests:
            return {}

        system_prompt = f"""You are extracting table values from a real estate PDF for specific YAML schema tables.

Below is the complete list of key-value pairs, full tables, and narratives extracted by Azure Document Intelligence:

```json
{pdf_fields_json}
```

{TABLE_HEADER_EQUIVALENTS}

For each requested schema table:
- If `column_map` is provided, use it to map schema columns to PDF headers.
- If `column_map_coverage` is low, you may infer additional columns using header similarity, but do NOT guess.
- Use the row labels if provided (these match the Excel row identifier column).
- If no row labels are provided, return rows in the order they appear in the PDF.
- For each row, return a `values` map keyed by `excel_column` (e.g., "K", "M", "N").
- Return null for any value that cannot be confidently found in the PDF.
- Never fabricate values (e.g., do NOT invent # Units if the column is missing).
"""

        user_message = (
            f"Extract values for these {len(table_requests)} schema tables.\n\n"
            f"Tables to extract:\n```json\n{json.dumps(table_requests, indent=2)}\n```\n\n"
            f"Rules:\n"
            f"- `row_index` is 0-based within the table's data range.\n"
            f"- `row_label` should match one of the provided row_labels if available.\n"
            f"- Values must respect data_type: number, currency, percentage, date, text.\n"
            f"- Use `column_map` when provided; leave missing columns as null.\n"
            f"- Provide citations like [S1:p5] and a brief reasoning per row (reasoning is required).\n"
        )

        system_arg = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        message = await asyncio.to_thread(
            self.client.messages.parse,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.0,
            timeout=settings.synthesis_llm_timeout_seconds,
            system=system_arg,
            messages=[{"role": "user", "content": user_message}],
            output_format=SchemaTableExtractionResult,
        )

        parsed_output = message.parsed_output
        result = parsed_output.model_dump()

        result_dict: Dict[str, Any] = {}
        for table_result in result.get("results", []):
            table_id = table_result.get("table_id")
            if not table_id:
                continue
            result_dict[table_id] = {
                "rows": table_result.get("rows", [])
            }

        logger.info(
            f"🎯 Targeted table extraction complete: {len(result_dict)} tables, "
            f"{sum(len(v.get('rows', [])) for v in result_dict.values())} rows"
        )

        return result_dict

    async def extract_schema_table_values_rag(
        self,
        schema_table: Dict[str, Any],
        context_chunks: List[Dict[str, Any]],
        row_labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        RAG-based targeted extraction for a single schema table using retrieved chunks.
        """
        if not schema_table or not context_chunks:
            return {}

        table_id = schema_table.get("id")
        if not table_id:
            return {}

        row_labels = row_labels or []
        context_payload = self._build_table_rag_text_context(context_chunks)
        context_json = json.dumps(context_payload, separators=(",", ":"), ensure_ascii=False)

        columns = [
            {
                "excel_column": c.get("excel_column"),
                "header": c.get("header"),
                "data_type": c.get("data_type", "text"),
                "pdf_aliases": c.get("pdf_aliases", []),
            }
            for c in schema_table.get("columns", [])
        ]

        table_request = {
            "table_id": table_id,
            "sheet": schema_table.get("sheet"),
            "data_start_row": schema_table.get("data_start_row"),
            "data_end_row": schema_table.get("data_end_row", schema_table.get("data_start_row")),
            "row_identifier_column": schema_table.get("row_identifier_column"),
            "row_labels": row_labels,
            "columns": columns,
        }

        pair = self.prompts.build_extract_table_values_rag_single(context_json, table_request)

        system_arg = [
            {
                "type": "text",
                "text": pair.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        t0 = time.time()
        response = await asyncio.to_thread(
            self.client.messages.create,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.0,
            timeout=settings.synthesis_llm_timeout_seconds,
            system=system_arg,
            messages=[{"role": "user", "content": pair.user_message}],
        )

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text)

        try:
            raw_result = json.loads(raw_text)
            parsed = SchemaTableExtractionResult(**raw_result)
            raw_result = parsed.model_dump()
        except Exception as e:
            logger.error(f"Failed to parse table extraction response: {e}\nRaw: {raw_text[:500]}")
            return {}

        result_dict: Dict[str, Any] = {}
        results = raw_result.get("results") if isinstance(raw_result, dict) else None
        if isinstance(results, list):
            for table_result in results:
                if table_result.get("table_id") == table_id:
                    result_dict[table_id] = {
                        "rows": table_result.get("rows", []),
                    }
                    break
        elif isinstance(raw_result, dict) and raw_result.get("table_id") == table_id:
            result_dict[table_id] = {"rows": raw_result.get("rows", [])}

        usage = response.usage
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        # Record metrics
        self._record_llm_metrics(input_tokens, output_tokens, cache_read, cache_creation)

        if self.capture_io_log and self._io_log_repo:
            self._io_log_repo.save_io_log(
                source_type="template_fill",
                source_id=self.fill_run_id,
                stage="extract_table_values_rag_single",
                prompt_version=self.prompts.version,
                # system_prompt stored here — context_json is ephemeral (not reconstructible from fill run)
                system_prompt=pair.system_prompt,
                user_message=pair.user_message,
                output=result_dict,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_tokens=cache_creation,
                cache_read_tokens=cache_read,
                duration_ms=int((time.time() - t0) * 1000),
            )

        return result_dict

    async def extract_schema_table_values_rag_batch(
        self,
        schema_tables: List[Dict[str, Any]],
        context_chunks: List[Dict[str, Any]],
        row_labels_by_table: Optional[Dict[str, List[str]]] = None,
        prebuilt_context_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        RAG-based targeted extraction for a batch of schema tables using retrieved chunks.

        Pass prebuilt_context_json when calling in a loop with the same context_chunks across
        all iterations — avoids rebuilding and re-serializing the context on every call.
        """
        if not schema_tables or not context_chunks:
            return {}

        row_labels_by_table = row_labels_by_table or {}
        if prebuilt_context_json is not None:
            context_json = prebuilt_context_json
        elif context_chunks[0].get("source"):
            # pdf_fields from detect_fields_task (have "source" key); raw chunk dicts do not
            context_json = json.dumps(
                self._build_table_context_from_pdf_fields(context_chunks),
                separators=(",", ":"), ensure_ascii=False,
            )
        else:
            context_json = json.dumps(
                self._build_table_rag_text_context(context_chunks),
                separators=(",", ":"), ensure_ascii=False,
            )

        table_requests = []
        for schema_table in schema_tables:
            table_id = schema_table.get("id")
            if not table_id:
                continue
            row_labels = row_labels_by_table.get(table_id, [])
            columns = [
                {
                    "excel_column": c.get("excel_column"),
                    "header": c.get("header"),
                    "data_type": c.get("data_type", "text"),
                    "pdf_aliases": c.get("pdf_aliases", []),
                }
                for c in schema_table.get("columns", [])
            ]
            table_requests.append({
                "table_id": table_id,
                "sheet": schema_table.get("sheet"),
                "data_start_row": schema_table.get("data_start_row"),
                "data_end_row": schema_table.get("data_end_row", schema_table.get("data_start_row")),
                "row_identifier_column": schema_table.get("row_identifier_column"),
                "row_labels": row_labels,
                "columns": columns,
            })

        if not table_requests:
            return {}

        # Build prompt pair from versioned prompt set
        pair = self.prompts.build_extract_table_values_rag(
            context_json, table_requests, TABLE_HEADER_EQUIVALENTS
        )
        system_prompt = pair.system_prompt
        user_message = pair.user_message

        system_arg = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        # USE messages.create instead of messages.parse (table extraction)
        t0 = time.time()
        response = await asyncio.to_thread(
            self.client.messages.create,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.0,
            timeout=settings.synthesis_llm_timeout_seconds,
            system=system_arg,
            messages=[{"role": "user", "content": user_message}],
        )
        duration_ms = int((time.time() - t0) * 1000)

        # Parse the text response manually
        raw_text = response.content[0].text.strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text)

        try:
            raw_result = json.loads(raw_text)
            parsed = SchemaTableExtractionResult(**raw_result)
            result = parsed.model_dump()
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse table extraction response: {e}\nRaw: {raw_text[:500]}")
            return {}

        # Token usage
        usage = getattr(response, "usage", None)
        input_tokens = output_tokens = cache_creation = cache_read = 0
        if usage is not None:
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        if self.capture_io_log and self._io_log_repo:
            self._io_log_repo.save_io_log(
                source_type="template_fill",
                source_id=self.fill_run_id,
                stage="extract_table_values_rag",
                prompt_version=self.prompts.version,
                system_prompt=system_prompt,
                user_message=user_message,
                output=result,
                metadata={"table_ids": [r.get("table_id") for r in table_requests]},
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_tokens=cache_creation,
                cache_read_tokens=cache_read,
                duration_ms=duration_ms,
            )

        result_dict: Dict[str, Any] = {}
        for table_result in result.get("results", []):
            table_id = table_result.get("table_id")
            if not table_id:
                continue
            result_dict[table_id] = {
                "rows": table_result.get("rows", []),
            }

        return result_dict

    def _format_chunks_with_citations(self, chunks: List[Dict[str, Any]]) -> str:
        """Format chunks with citation tokens for LLM consumption."""
        formatted_parts = []

        for i, chunk in enumerate(chunks):
            page_num = self._resolve_chunk_page(chunk)
            citation = f"[S{i+1}:p{page_num}]" if page_num > 0 else chunk.get("citation", "[?]")
            text = chunk.get("text", "")
            section = chunk.get("section_heading", "")
            is_table = chunk.get("is_tabular", False)

            chunk_type = "Table" if is_table else "Text"
            header = f"--- {chunk_type} Chunk {i+1} (Page {page_num}"
            if section:
                header += f", Section: {section}"
            header += ") ---"

            formatted_text = f"{citation} {text}"
            formatted_parts.append(f"{header}\n{formatted_text}\n")

        return "\n".join(formatted_parts)

    def _resolve_chunk_page(self, chunk: Dict[str, Any]) -> int:
        """
        Resolve the most accurate display page for a chunk.

        Priority:
        1) chunk_metadata.bbox.page
        2) chunk_metadata.page_number
        3) chunk_metadata.page_range[0]
        4) chunk.page_number (DB column fallback; may be first page for multi-page chunks)
        """
        metadata = chunk.get("chunk_metadata") or chunk.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        if isinstance(metadata, dict):
            bbox = metadata.get("bbox")
            if isinstance(bbox, dict):
                bbox_page = bbox.get("page")
                if isinstance(bbox_page, int) and bbox_page > 0:
                    return bbox_page
                if isinstance(bbox_page, str) and bbox_page.isdigit():
                    return int(bbox_page)

            metadata_page = metadata.get("page_number")
            if isinstance(metadata_page, int) and metadata_page > 0:
                return metadata_page
            if isinstance(metadata_page, str) and metadata_page.isdigit():
                return int(metadata_page)

            page_range = metadata.get("page_range")
            if isinstance(page_range, list) and page_range:
                first_page = page_range[0]
                if isinstance(first_page, int) and first_page > 0:
                    return first_page
                if isinstance(first_page, str) and first_page.isdigit():
                    return int(first_page)

        fallback_page = chunk.get("page_number")
        if isinstance(fallback_page, int) and fallback_page > 0:
            return fallback_page
        if isinstance(fallback_page, str) and fallback_page.isdigit():
            return int(fallback_page)

        return 0

    async def auto_map_fields(
        self,
        pdf_fields: List[Dict[str, Any]],
        excel_schema: Dict[str, Any],
        on_batch_complete=None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Automatically map PDF fields to Excel cells using sheet batching.

        Uses Anthropic's Structured Outputs to GUARANTEE valid JSON response.

        **Optimized Sheet Batching Strategy (fixes 200k token overflow):**
        - System prompt: Instructions + ALL PDF fields (cached once, ~12k tokens)
        - Batches Excel sheets into groups of 4 sheets
        - User message: Compressed sheet batch (~9k tokens per batch)
        - Total per call: ~12k (cached) + ~9k (user) = ~21k tokens
        - Total calls: ~6 calls for 21 sheets (vs 9 calls with old PDF batching)

        **Token Efficiency:**
        - PDF fields cached once, reused across all sheet batches
        - Each sheet batch creates unique user message
        - Avoids 200k+ token overflow from sending full schema

        Args:
            pdf_fields: List of detected PDF fields (from Azure DI)
            excel_schema: Excel template schema (all sheets)
            on_batch_complete: Optional callback(batch_num, total_batches, batch_mappings)
            use_cache: Enable prompt caching (default: True)

        Returns:
            {
                "mappings": [...],
                "total_mapped": 38,
                "high_confidence_count": 25,
                ...
            }
        """
        logger.info(
            f"🔄 Auto-mapping {len(pdf_fields)} PDF fields across "
            f"{len(excel_schema.get('sheets', []))} sheets (sheet batching strategy)"
        )

        if not pdf_fields or not excel_schema.get("sheets"):
            return {"mappings": [], "total_mapped": 0, "total_unmapped": 0, "high_confidence_count": 0}

        # Batch sheets (not PDF fields) to stay under token limits
        SHEETS_PER_BATCH = 4

        try:
            all_mappings = []
            total_high_confidence = 0

            # Track aggregated token usage across all batches
            total_input_tokens = 0
            total_output_tokens = 0
            total_cache_creation_tokens = 0
            total_cache_read_tokens = 0

            # Step 1: Compress full Excel schema
            compressed_schema = self._compress_excel_schema(excel_schema)
            sheets = compressed_schema.get("sheets", [])
            total_sheets = len(sheets)
            total_batches = (total_sheets + SHEETS_PER_BATCH - 1) // SHEETS_PER_BATCH

            logger.info(
                f"📊 Batching strategy: {total_sheets} sheets / {SHEETS_PER_BATCH} per batch = "
                f"{total_batches} LLM calls"
            )

            # Step 2: Build system prompt with ALL PDF fields (cached once, reused)
            stripped_fields = [self._strip_pdf_field(field) for field in pdf_fields]
            pdf_fields_json = json.dumps(stripped_fields, separators=(",", ":"), ensure_ascii=False)
            system_prompt = self.prompts.build_auto_map_system(pdf_fields_json)

            # Estimate and log token counts
            system_tokens = count_tokens(system_prompt)
            logger.info(
                f"📝 System prompt (PDF fields): ~{system_tokens:,} tokens "
                f"({len(stripped_fields)} fields, will be cached)"
            )

            # Step 3: Process Excel sheets in batches
            for i in range(0, total_sheets, SHEETS_PER_BATCH):
                sheet_batch = sheets[i:i + SHEETS_PER_BATCH]
                batch_num = (i // SHEETS_PER_BATCH) + 1
                sheet_names = [s.get("name", f"Sheet{idx}") for idx, s in enumerate(sheet_batch, start=i)]

                logger.info(
                    f"\n📋 Batch {batch_num}/{total_batches}: Processing {len(sheet_batch)} sheets: "
                    f"{', '.join(sheet_names[:3])}{'...' if len(sheet_names) > 3 else ''}"
                )

                # Build sheet batch schema
                sheet_batch_schema = self._extract_sheet_batch_schema(compressed_schema, sheet_batch)
                user_message = self.prompts.build_auto_map_user(sheet_batch_schema)

                # Estimate and log token counts for this batch
                user_tokens = count_tokens(user_message)
                total_tokens = system_tokens + user_tokens
                logger.info(
                    f"   📊 Tokens: system ~{system_tokens:,} (cached) + "
                    f"user ~{user_tokens:,} = ~{total_tokens:,} total"
                )

                # Warn if approaching limit
                if total_tokens > 150000:
                    logger.warning(
                        f"⚠️  Batch {batch_num} approaching token limit: {total_tokens:,} tokens "
                        f"(max 200k). Consider reducing SHEETS_PER_BATCH."
                    )

                # Build cached system prompt
                system_arg: Any
                if use_cache:
                    system_arg = [
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
                else:
                    system_arg = system_prompt

                # Use Anthropic Structured Outputs
                t0 = time.time()
                message = await asyncio.to_thread(
                    self.client.messages.parse,
                    model=self.model,
                    max_tokens=settings.synthesis_llm_max_tokens,
                    temperature=0.0,
                    timeout=settings.synthesis_llm_timeout_seconds,
                    system=system_arg,
                    messages=[{"role": "user", "content": user_message}],
                    output_format=self.prompts.get_auto_map_response_model(),
                )
                batch_duration_ms = int((time.time() - t0) * 1000)

                # Log actual cache usage from Anthropic and accumulate totals
                usage = getattr(message, "usage", None)
                if usage is not None:
                    cache_creation = getattr(usage, "cache_creation_input_tokens", None) or 0
                    cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
                    input_tokens = getattr(usage, "input_tokens", None) or 0
                    output_tokens = getattr(usage, "output_tokens", None) or 0

                    # Record metrics for this batch
                    self._record_llm_metrics(input_tokens, output_tokens, cache_read, cache_creation)

                    # Accumulate token totals across all batches
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    total_cache_creation_tokens += cache_creation
                    total_cache_read_tokens += cache_read

                    if cache_creation > 0 or cache_read > 0:
                        logger.info(
                            f"   💾 Cache stats: creation={cache_creation:,}, read={cache_read:,}, "
                            f"input={input_tokens:,}, output={output_tokens:,}"
                        )

                parsed_output = message.parsed_output
                batch_result = parsed_output.model_dump()

                # Collect mappings from this batch
                batch_mappings = batch_result.get("mappings", [])
                all_mappings.extend(batch_mappings)
                total_high_confidence += batch_result.get("high_confidence_count", 0)

                logger.info(
                    f"   ✅ Batch {batch_num}/{total_batches} complete: "
                    f"{len(batch_mappings)} mappings, "
                    f"{batch_result.get('high_confidence_count', 0)} high confidence"
                )

                if self.capture_io_log and self._io_log_repo:
                    self._io_log_repo.save_io_log(
                        source_type="template_fill",
                        source_id=self.fill_run_id,
                        stage=f"auto_map_fields_batch_{batch_num}",
                        prompt_version=self.prompts.version,
                        user_message=user_message,
                        output=batch_result,
                        input_tokens=input_tokens if usage else 0,
                        output_tokens=output_tokens if usage else 0,
                        cache_creation_tokens=cache_creation if usage else 0,
                        cache_read_tokens=cache_read if usage else 0,
                        duration_ms=batch_duration_ms,
                    )

                # Call progress callback if provided
                if on_batch_complete:
                    on_batch_complete(batch_num, total_batches, batch_mappings)

            # Aggregate results
            result = {
                "mappings": all_mappings,
                "total_mapped": len(all_mappings),
                "total_unmapped": len(pdf_fields) - len(all_mappings),
                "high_confidence_count": total_high_confidence,
                # Token usage data for observability
                "usage": {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cache_creation_input_tokens": total_cache_creation_tokens,
                    "cache_read_input_tokens": total_cache_read_tokens,
                    "total_batches": total_batches,
                    "model": self.model,
                }
            }

            # Add status to all mappings
            for mapping in result.get("mappings", []):
                if "status" not in mapping:
                    mapping["status"] = "auto_mapped"

            logger.info(
                f"\n✅ Auto-mapping complete: {result.get('total_mapped', 0)} total mappings across "
                f"{total_sheets} sheets ({result.get('high_confidence_count', 0)} high confidence, "
                f"{result.get('total_unmapped', 0)} unmapped) | "
                f"Tokens: input={total_input_tokens:,}, output={total_output_tokens:,}, "
                f"cache_read={total_cache_read_tokens:,}"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Error auto-mapping fields: {e}", exc_info=True)
            raise

    def _compress_excel_schema(self, excel_schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress Excel schema to reduce token usage by ~70-80%.

        Removes verbose metadata while keeping essential mapping information:
        - Limits fillable_cells to max 20 samples per table
        - Removes: column_headers_detailed, current_value, is_merged, data_rows
        - Keeps: cell, label, type, col_header, row_label, sheet name

        This allows large templates (1200+ fields, 30+ tables) to fit within token limits.
        """
        compressed = {
            "total_key_value_fields": excel_schema.get("total_key_value_fields", 0),
            "total_tables": excel_schema.get("total_tables", 0),
            "has_formulas": excel_schema.get("has_formulas", False),
            "sheets": []
        }

        for sheet in excel_schema.get("sheets", []):
            compressed_sheet = {
                "name": sheet.get("name"),
                "index": sheet.get("index"),
            }

            # Compress key-value fields (remove current_value, is_merged)
            kv_fields = sheet.get("key_value_fields", [])
            compressed_sheet["key_value_fields"] = [
                {
                    "cell": kv.get("cell"),
                    "label": kv.get("label"),
                    "type": kv.get("type"),
                    "row": kv.get("row"),
                    "col": kv.get("col"),
                }
                for kv in kv_fields
            ]

            # Compress tables (limit fillable_cells to 20, remove verbose metadata)
            tables = sheet.get("tables", [])
            compressed_tables = []
            for table in tables:
                # Limit fillable_cells to max 20 samples (instead of 100)
                fillable_cells = table.get("fillable_cells", [])[:20]

                compressed_table = {
                    "table_name": table.get("table_name"),
                    "start_row": table.get("start_row"),
                    "start_col": table.get("start_col"),
                    "end_col": table.get("end_col"),
                    "column_headers": table.get("column_headers", []),  # Keep hierarchical headers
                    "total_fillable_cells": table.get("total_fillable_cells", 0),
                    # Simplified fillable_cells (remove col_letter, keep essentials)
                    "fillable_cells": [
                        {
                            "cell": cell.get("cell"),
                            "row": cell.get("row"),
                            "col": cell.get("col"),
                            "row_label": cell.get("row_label"),
                            "col_header": cell.get("col_header"),
                            "type": cell.get("type"),
                        }
                        for cell in fillable_cells
                    ]
                }
                compressed_tables.append(compressed_table)

            compressed_sheet["tables"] = compressed_tables
            compressed["sheets"].append(compressed_sheet)

        logger.info(
            f"Compressed Excel schema: {len(excel_schema.get('sheets', []))} sheets, "
            f"{compressed['total_key_value_fields']} KV fields, {compressed['total_tables']} tables"
        )

        return compressed

    def _strip_pdf_field(self, field: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove unnecessary fields from PDF field to reduce tokens (~26% reduction).

        Removes: description, source (not used by mapping logic)
        Keeps: id, name, type, extracted_value, confidence, citations (all required)
        For table_block fields: also keeps table_name, table_columns, table_rows (full context)
        For narrative_block fields: also keeps full_text and section (rich context for LLM)
        """
        stripped = {
            "id": field.get("id"),
            "name": field.get("name"),
            "type": field.get("type"),
            "extracted_value": field.get("extracted_value"),
            "confidence": field.get("confidence"),
            "citations": field.get("citations", []),
        }
        # Preserve full table structure for table_block fields
        if field.get("type") == "table":
            if field.get("table_name"):
                stripped["table_name"] = field.get("table_name")
            if field.get("table_columns"):
                stripped["table_columns"] = field.get("table_columns")
            if field.get("table_rows"):
                stripped["table_rows"] = field.get("table_rows")
        # Preserve full narrative text for narrative_block fields
        elif field.get("type") == "narrative":
            if field.get("full_text"):
                stripped["full_text"] = field.get("full_text")
            if field.get("section"):
                stripped["section"] = field.get("section")
        return stripped

    def _build_table_context_from_pdf_fields(self, pdf_fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build table extraction context from pdf_fields (detect_fields_task output).

        Uses the same structured data Stage 1.5 (extract_schema_field_values) already sends to the LLM.
        Passing the same pdf_fields across all table batch calls means the system prompt is identical
        each time — enabling Anthropic prompt cache hits (~10x cheaper after the first call).
        """
        context = []
        for f in pdf_fields:
            source = f.get("source")
            if source not in ("key_value_pairs", "table_block", "narrative_block"):
                continue
            if source == "table_block":
                page_number = f.get("page_number")
                cols = f.get("table_columns", [])
                rows = f.get("table_rows", [])
                text = f.get("name", "") + "\n" + " | ".join(str(c) for c in cols) + "\n"
                text += "\n".join(" | ".join(str(v) for v in row) for row in rows)
            elif source == "narrative_block":
                page_number = f.get("page_number")
                text = f.get("full_text") or f.get("extracted_value") or ""
            else:  # key_value_pairs — bbox.page is exact (Azure DI per-pair bounding_regions)
                page_number = (f.get("bbox", {}) or {}).get("page") or f.get("page_number")
                text = f"{f.get('name', '')}: {f.get('extracted_value', '')}"
            context.append({"text": text, "page_number": page_number, "section_type": source})
        return context

    def _build_table_rag_text_context(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build text-only RAG context from retrieved chunks for table extraction.
        Uses DocumentChunk.text + page metadata only.
        """
        context: List[Dict[str, Any]] = []
        for chunk in chunks:
            metadata = chunk.get("chunk_metadata") or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}

            page_range = metadata.get("page_range")
            bbox_page = (metadata.get("bbox", {}) or {}).get("page")
            if bbox_page:
                # Table chunks — bbox.page is the exact page
                page_number = bbox_page
            elif isinstance(page_range, list) and len(page_range) >= 2 and page_range[0] != page_range[-1]:
                # Multi-page KV chunk — chunk.page_number is only the start, not reliable
                page_number = None
            else:
                page_number = chunk.get("page_number") or metadata.get("page_number")

            context.append({
                "text": chunk.get("text") or "",
                "page_number": page_number,
                "section_type": chunk.get("section_type") or metadata.get("chunk_type"),
            })

        return context

    def _extract_sheet_batch_schema(
        self,
        full_schema: Dict[str, Any],
        sheet_batch: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract a subset of sheets from the full compressed schema.

        Args:
            full_schema: Full compressed Excel schema
            sheet_batch: List of sheet dicts to extract

        Returns:
            Schema with only the specified sheets
        """
        return {
            "total_key_value_fields": sum(
                len(s.get("key_value_fields", [])) for s in sheet_batch
            ),
            "total_tables": sum(
                len(s.get("tables", [])) for s in sheet_batch
            ),
            "has_formulas": full_schema.get("has_formulas", False),
            "sheets": sheet_batch
        }

    # _build_system_prompt_with_pdf_fields and _build_sheet_batch_user_message
    # moved to prompts/v1.py (build_auto_map_system / build_auto_map_user)

