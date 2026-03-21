"""LLM service for template filling: field detection, auto-mapping, and data extraction.

Uses Anthropic's Structured Outputs feature to GUARANTEE valid JSON responses.
"""

import asyncio
import json
import re
import hashlib
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from urllib import response

from anthropic import Anthropic
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings
from app.core.redis_client import get_redis_client_for_cache
from app.utils.logging import logger

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
# Pydantic Schemas for Structured Outputs
# ============================================================================

class DetectedField(BaseModel):
    """Schema for a single detected field from PDF."""
    name: str = Field(description="Clear, descriptive field name")
    type: str = Field(description="Data type: text, number, currency, percentage, date")
    extracted_value: str = Field(description="Actual value found in the PDF")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in extraction (0.0-1.0)")
    citations: List[str] = Field(description="Citation tokens where field was found (e.g., ['[D1:p2]'])")
    description: str = Field(description="Brief explanation of what this field represents")


class FieldDetectionResult(BaseModel):
    """Schema for field detection response."""
    fields: List[DetectedField] = Field(description="List of detected fields")
    total_fields: int = Field(description="Total number of fields detected")
    categories: List[str] = Field(description="Field categories (property_info, financial_metrics, etc.)")


class FieldMapping(BaseModel):
    """Schema for a single field mapping."""
    pdf_field_id: str = Field(description="ID of the PDF field")
    pdf_field_name: str = Field(description="Name of the PDF field")
    excel_cell: str = Field(description="Excel cell reference (e.g., 'B2')")
    excel_sheet: str = Field(description="Excel sheet name")
    excel_label: str = Field(description="Label/description from Excel")
    confidence: float = Field(ge=0.0, le=1.0, description="Mapping confidence (0.0-1.0)")
    citations: List[str] = Field(description="Citation tokens from PDF field")
    reasoning: str = Field(description="Explanation of why this mapping was made")


class AutoMappingResult(BaseModel):
    """Schema for auto-mapping response."""
    mappings: List[FieldMapping] = Field(description="List of field mappings")
    total_mapped: int = Field(description="Number of successfully mapped fields")
    total_unmapped: int = Field(description="Number of unmapped fields")
    high_confidence_count: int = Field(description="Number of high-confidence mappings (>0.8)")


class ExtractedFieldValue(BaseModel):
    """Schema for a single extracted field value."""
    value: Optional[str] = Field(description="Extracted value (null if not found)")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence")
    citations: List[str] = Field(description="Citation tokens where value was found")
    source_text: str = Field(description="Brief snippet of surrounding text for context")


class SchemaFieldResult(BaseModel):
    """Extraction result for a single YAML schema field (Stage 2 targeted extraction)."""
    field_id: str = Field(description="Schema field ID (from YAML)")
    value: Optional[str] = Field(None, description="Extracted value, null if not found in PDF")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence (0.0-1.0)")
    citations: List[str] = Field(default_factory=list, description="Citation tokens like [D1:p5]")
    reasoning: Optional[str] = Field(None, description="AI reasoning for this extraction (e.g., 'Found in KV pair', 'Extracted from Table X, column Y')")


class SchemaFieldExtractionResult(BaseModel):
    """Result of Stage 2 targeted schema field extraction."""
    results: List[SchemaFieldResult] = Field(description="Results for each requested schema field")
    total_found: int = Field(description="Number of fields with non-null values found")
    total_not_found: int = Field(description="Number of fields not found in PDF")


class SchemaTableRowResult(BaseModel):
    """Extraction result for a single table row in a YAML schema table."""
    row_index: int = Field(description="0-based row index within the schema table data range")
    row_label: Optional[str] = Field(None, description="Row label if provided (matches Excel row identifier column)")
    values: Dict[str, Optional[str]] = Field(
        description="Map of excel_column -> extracted value. "
                    "MUST include all columns from the schema. "
                    "Use null only if genuinely not found."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence for this row")
    citations: List[str] = Field(default_factory=list, description="Citation tokens like [D1:p5]")
    reasoning: Optional[str] = Field(None, description="AI reasoning for this row extraction (e.g., 'Matched row label', 'Extracted from Table X with column mapping')" )

    @field_validator("values", mode="before")
    @classmethod
    def coerce_values_to_str(cls, v: Any) -> Dict[str, Optional[str]]:
        if not isinstance(v, dict):
            return v
        return {
            k: str(val) if val is not None else None
            for k, val in v.items()
        }


class SchemaTableResult(BaseModel):
    """Extraction result for a single YAML schema table."""
    table_id: str = Field(description="Schema table ID")
    rows: List[SchemaTableRowResult] = Field(description="Extracted rows for this table")


class SchemaTableExtractionResult(BaseModel):
    """Result of Stage 2 targeted schema table extraction."""
    results: List[SchemaTableResult] = Field(description="Results for each requested schema table")
    total_tables: int = Field(description="Number of tables processed")
    total_rows: int = Field(description="Total rows returned across all tables")


# ============================================================================
# LLM Service
# ============================================================================

class TemplateFillLLMService:
    """LLM service for intelligent template filling operations with guaranteed valid JSON."""

    def __init__(self):
        """Initialize LLM service with Anthropic client."""
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.synthesis_llm_model  # Use Haiku 4.5 for cost-effective template filling
        # Use Haiku's max output (16,384 tokens) for large PDFs
        self.max_tokens = settings.synthesis_llm_max_tokens

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

        # Format chunks with citations
        context = self._format_chunks_with_citations(chunks_with_metadata)

        prompt = self._build_field_detection_prompt(context)

        try:
            # Use Anthropic Structured Outputs - GUARANTEES valid JSON!
            message = await asyncio.to_thread(
                self.client.messages.parse,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.0,
                timeout=settings.synthesis_llm_timeout_seconds,
                messages=[{"role": "user", "content": prompt}],
                output_format=FieldDetectionResult
            )

            # Extract validated response (already guaranteed to match schema!)
            parsed_output = message.parsed_output
            result = parsed_output.model_dump()

            logger.info(f"✅ Detected {len(result.get('fields', []))} fields from PDF (structured output)")

            # Add IDs to fields
            for idx, field in enumerate(result.get("fields", []), start=1):
                if "id" not in field:
                    field["id"] = f"f{idx}"

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

        # System prompt: all Azure DI data (cached across any follow-up calls)
#         system_prompt = f"""You are extracting values from a real estate PDF for specific named schema fields.

# Below is the complete list of key-value pairs, full tables, and market context (narratives) extracted by Azure Document Intelligence:

# ```json
# {pdf_fields_json}
# ```

# For each requested schema field, find its value from the Azure DI data above.
# Match by the field's aliases and semantic meaning. For example:
# - A field with aliases ["City", "Location City"] might appear as "City:", "Location:", "Property City", etc.
# - A field with aliases ["Asking Price", "Purchase Price"] might appear as "List Price", "Sale Price", etc.

# Return null for value if the data genuinely cannot be found in the PDF."""
        
        system_prompt = f"""You are extracting values from a real estate PDF for specific named schema fields.

Below is the complete list of key-value pairs, full tables, and market context (narratives) extracted by Azure Document Intelligence:
```json
{pdf_fields_json}
```

For each requested schema field, find its value from the Azure DI data above.
Match by the field's aliases and semantic meaning. For example:
- A field with aliases ["City", "Location City"] might appear as "City:", "Location:", "Property City", etc.
- A field with aliases ["Asking Price", "Purchase Price"] might appear as "List Price", "Sale Price", etc.

Be aggressive in matching — if a value is semantically equivalent to an alias, extract it.
Return null only if the value genuinely cannot be found anywhere in the PDF data."""

        # User message: list of fields to extract (minimal token footprint)
        fields_for_request = [
            {
                "id": f["id"],
                "aliases": f.get("pdf_aliases", []),
                "data_type": f.get("data_type", "text"),
            }
            for f in unmapped_fields
        ]
        user_message = (
            f"Find values for these {len(fields_for_request)} schema fields from the Azure DI data "
            f"in the system prompt.\n\n"
            f"Fields to extract:\n```json\n"
            f"{json.dumps(fields_for_request, indent=2)}\n```\n\n"
            f"IMPORTANT - Data Type Validation Rules:\n"
            f"- currency: Must be numeric with $ sign (e.g., '$450,000'). Return null for non-numeric text.\n"
            f"- number: Must be numeric (e.g., '100', '3.14'). Return null for non-numeric text.\n"
            f"- percentage: Must include % (e.g., '65%', '8.11%'). Return null if not a percentage.\n"
            f"- date: Must be a date (e.g., '2026-03-10', 'March 10, 2026'). Return null for non-dates.\n"
            f"- text: Any text value is acceptable.\n\n"
            f"CRITICAL: You MUST attempt to find a value for every single field. "
            f"Do not skip fields. If a field has multiple possible aliases, try all of them. "
            f"Only return null if the value is truly absent from the PDF data.\n\n"
            f"Return ONLY a JSON object matching this exact structure, no markdown:\n"
            "{\n"
            '  "results": [\n'
            "    {\n"
            '      "field_id": "field_id_here",\n'
            '      "value": "extracted value or null",\n'
            '      "confidence": 0.95,\n'
            '      "citations": ["[D1:p3]"],\n'
            '      "reasoning": "Found as currency: $2,500,000 in KV pair Listing Price"\n'
            "    }\n"
            "  ],\n"
            f'  "total_found": 10,\n'
            f'  "total_not_found": 2\n'
            "}\n"
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
            output_format=SchemaFieldExtractionResult,
        )

        # Log token usage
        usage = getattr(message, "usage", None)
        if usage is not None:
            cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            logger.info(
                f"🎯 Stage 2 tokens: input={input_tokens:,}, output={output_tokens:,}, "
                f"cache_creation={cache_creation:,}, cache_read={cache_read:,}"
            )

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
    #         '      "citations": ["[D1:p3]"],\n'
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
            f"- Provide citations like [D1:p5] and a brief reasoning per row (reasoning is required).\n"
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
            temperature=0.1,
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

        system_prompt = f"""You are extracting table values from a real estate PDF for a single YAML schema table.

You are given a small, high-signal set of retrieved chunks (tables + key-value pairs).
Use ONLY this context to extract values. Do not guess.

Retrieved context:
```json
{context_json}
```

{TABLE_HEADER_EQUIVALENTS}
"""

        user_message = (
            "Extract values for this schema table:\n\n"
            f"```json\n{json.dumps(table_request, indent=2)}\n```\n\n"
            "Rules:\n"
            "- Use `excel_column` keys only in the `values` map.\n"
            "- If a column is missing, return null for that column.\n"
            "- Use row_labels when provided; if row_labels are empty or blank, ignore them and use row_index order.\n"
            "- Provide citations like [D1:p5] and a brief reasoning per row (reasoning is required).\n"
            "- Never fabricate values.\n"
            "\nCRITICAL: For each row, the `values` dict MUST include ALL excel_column keys "
            "listed in the table's `columns` array. "
            "Example: if columns are G, H, I then values must be "
            '{"G": "5 x 10", "H": "26", "I": "50"} — never return an empty {}.\n'
            "\nReturn ONLY a JSON object matching this exact structure, no markdown:\n"
            "{\n"
            '  "results": [\n'
            "    {\n"
            '      "table_id": "...",\n'
            '      "rows": [\n'
            "        {\n"
            '          "row_index": 0,\n'
            '          "row_label": null,\n'
            '          "values": {"G": "5 x 10", "H": "26", "I": "50"},\n'
            '          "confidence": 0.95,\n'
            '          "citations": ["[D1:p15]"],\n'
            '          "reasoning": "Extracted from Table 7"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ],\n"
            '  "total_tables": 1,\n'
            '  "total_rows": 12\n'
            "}\n"
        )

        system_arg = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        response = await asyncio.to_thread(
            self.client.messages.create,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.1,
            timeout=settings.synthesis_llm_timeout_seconds,
            system=system_arg,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text)

        try:
            raw_result = json.loads(raw_text)
            # Validate through Pydantic (handles int->str coercion via field_validator)
            parsed = SchemaTableExtractionResult(**raw_result)
            raw_result = parsed.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
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

        return result_dict

    async def extract_schema_table_values_rag_batch(
        self,
        schema_tables: List[Dict[str, Any]],
        context_chunks: List[Dict[str, Any]],
        row_labels_by_table: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        RAG-based targeted extraction for a batch of schema tables using retrieved chunks.
        """
        if not schema_tables or not context_chunks:
            return {}

        row_labels_by_table = row_labels_by_table or {}
        context_payload = self._build_table_rag_text_context(context_chunks)
        context_json = json.dumps(context_payload, separators=(",", ":"), ensure_ascii=False)

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

        system_prompt = f"""You are extracting table values from a real estate PDF for multiple YAML schema tables.

You are given a small, high-signal set of retrieved chunks (tables + key-value pairs).
Use ONLY this context to extract values. Do not guess.

Retrieved context:
```json
{context_json}
```

{TABLE_HEADER_EQUIVALENTS}
"""

        # user_message = (
        #     "Extract values for these schema tables:\n\n"
        #     f"```json\n{json.dumps(table_requests, indent=2)}\n```\n\n"
        #     "Rules:\n"
        #     "- Return results per table_id.\n"
        #     "- Use `excel_column` keys only in the `values` map.\n"
        #     "- If a column is missing, return null for that column.\n"
        #     "- Use row_labels when provided; if row_labels are empty or blank, ignore them and use row_index order.\n"
        #     "- Provide citations like [D1:p5] and a brief reasoning per row (reasoning is required).\n"
        #     "- Never fabricate values.\n"
        #     "\nCRITICAL: For each row, the `values` dict MUST include ALL excel_column keys "
        #     "listed in that table's `columns` array. "
        #     "Example: if columns are G, H, I then values must be "
        #     '{"G": "5 x 10", "H": "26", "I": "50"} — never return an empty {}.\n'
        # )

        user_message = (
            "Extract values for these schema tables and return a JSON object.\n\n"
            f"```json\n{json.dumps(table_requests, indent=2)}\n```\n\n"
            "Rules:\n"
            "- Return results per table_id.\n"
            "- Use `excel_column` keys only in the `values` map.\n"
            "- If a column is missing, return null for that column.\n"
            "- Use row_labels when provided; if row_labels are empty or blank, use row_index order.\n"
            "- Provide citations like [D1:p15] and reasoning per row.\n"
            "- Never fabricate values.\n"
            "- For each row, values MUST include ALL excel_column keys from that table's columns.\n\n"
            "Return ONLY a JSON object matching this exact structure, no markdown:\n"
            "{\n"
            '  "results": [\n'
            "    {\n"
            '      "table_id": "...",\n'
            '      "rows": [\n'
            "        {\n"
            '          "row_index": 0,\n'
            '          "row_label": null,\n'
            '          "values": {"G": "5 x 10", "H": "26", "I": "50"},\n'
            '          "confidence": 0.95,\n'
            '          "citations": ["[D1:p15]"],\n'
            '          "reasoning": "Extracted from Table 7 NON-CLIMATE rows"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ],\n"
            '  "total_tables": 2,\n'
            '  "total_rows": 12\n'
            "}\n"
        )

        system_arg = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        # USE messages.create instead of messages.parse
        response = await asyncio.to_thread(
            self.client.messages.create,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0.1,
            timeout=settings.synthesis_llm_timeout_seconds,
            system=system_arg,
            messages=[{"role": "user", "content": user_message}],
        )

        # Parse the text response manually
        raw_text = response.content[0].text.strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text)

        try:
            raw_result = json.loads(raw_text)
            # Validate through Pydantic
            parsed = SchemaTableExtractionResult(**raw_result)
            result = parsed.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Failed to parse table extraction response: {e}\nRaw: {raw_text[:500]}")
            return {}

        # message = await asyncio.to_thread(
        #     self.client.messages.parse,
        #     model=self.model,
        #     max_tokens=self.max_tokens,
        #     temperature=0.0,
        #     timeout=settings.synthesis_llm_timeout_seconds,
        #     system=system_arg,
        #     messages=[{"role": "user", "content": user_message}],
        #     output_format=SchemaTableExtractionResult,
        # )

        # parsed_output = message.parsed_output
        # result = parsed_output.model_dump()

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
            citation = f"[D1:p{page_num}]" if page_num > 0 else chunk.get("citation", "[?]")
            text = chunk.get("text", "")
            section = chunk.get("section_heading", "")
            is_table = chunk.get("is_tabular", False)

            chunk_type = "Table" if is_table else "Text"
            header = f"--- {chunk_type} Chunk {i+1} (Page {page_num}"
            if section:
                header += f", Section: {section}"
            header += f") ---"

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

    def _build_field_detection_prompt(self, pdf_context: str) -> str:
        """Build prompt for field detection."""
        return f"""You are analyzing a Real Estate offering memorandum (OM) or property document to extract all structured data fields.

Your task is to identify every piece of structured information that could be extracted and used to fill an Excel template.

**CRITICAL: Citation Format**
Each chunk in the PDF content is prefixed with a citation token like [D1:p5] (Document 1, Page 5).
You MUST include these citation tokens in your response to indicate where each field was found.

**CRITICAL: Chunk Metadata Usage**
Each chunk has metadata in the header:
- **Chunk Type**: "Table Chunk" contains structured/tabular data (often financial tables, rent rolls, unit mixes)
  - Table chunks are HIGH-VALUE for numeric fields (rents, areas, financials)
  - Extract all columns/rows from tables as separate fields
- **Chunk Type**: "Text Chunk" contains narrative/paragraph text (property descriptions, investment summary)
  - Text chunks contain property details, market analysis, qualitative data
- **Section Heading**: Indicates document section (e.g., "Financial Summary", "Property Overview")
  - Use section context to understand field meaning and categorization

**PDF Content:**
{pdf_context}

**Instructions:**

1. **Property Information** (typically in Text chunks, document headers):
   - Property Name, Property Address (Street, City, State, ZIP)
   - Property Type (Multifamily, Office, Retail, Industrial, Mixed-Use)
   - Year Built, Year Renovated
   - Number of Units, Number of Buildings
   - Total Square Footage (Rentable SF, Gross SF, Net SF)
   - Lot Size (Acres or SF), Zoning, Parcel Number
   - Ownership Type (Fee Simple, Leasehold)

2. **Financial Metrics** (HIGH PRIORITY - often in Table chunks, Operating Statements):
   - **Income Metrics:**
     - Gross Potential Rent (GPR), Gross Scheduled Income (GSI)
     - Loss to Lease, Vacancy Loss, Concessions
     - Effective Gross Income (EGI)
     - Other Income (Parking, Laundry, Pet Fees, RUBS, Late Fees)
   - **Expense Metrics:**
     - Total Operating Expenses
     - Individual Line Items: Property Taxes, Insurance, Utilities, R&M, Payroll, Management Fee, Marketing, Administrative, Contract Services, Turnover Costs, Reserves
   - **Performance Metrics:**
     - Net Operating Income (NOI)
     - Cap Rate (Capitalization Rate)
     - Price Per Unit, Price Per SF ($/SF, PSF)
     - Cash-on-Cash Return, IRR (Internal Rate of Return)
     - DSCR (Debt Service Coverage Ratio)
     - Operating Expense Ratio, Expense Per Unit, Expense Per SF

3. **Rent Roll Data** (often in Table chunks - extract EACH row as separate fields):
   - Unit Number, Unit Type (1BR, 2BR, Studio, etc.), Floor Plan
   - Square Footage (per unit)
   - In-Place Rent (Current Rent), Market Rent
   - Lease Start Date, Lease Expiration Date
   - Tenant Name (for commercial properties)
   - Rent Premium/Discount, Rent PSF

4. **Unit Mix / Floor Plan Summary** (Table chunks):
   - Unit Type, Count of Units, Average SF, Average Rent
   - Total Units by Bedroom Count

5. **Market Data**:
   - Occupancy Rate (Physical, Economic)
   - Market Vacancy Rate
   - Comparable Sales, Comparable Rents
   - Submarket Name, MSA

6. **Loan / Financing Terms** (if present):
   - Loan Amount, Interest Rate, Loan Term
   - Amortization Period, Loan-to-Value (LTV)
   - Debt Yield, Annual Debt Service

**For each field, provide:**
- name: Clear, descriptive field name using standard real estate terminology
- type: Data type (text, number, currency, percentage, date)
- extracted_value: The EXACT value found in the PDF (preserve original formatting)
- confidence: Your confidence in the extraction (0.0-1.0)
- citations: Array of citation tokens where this field was found
- description: Brief explanation of what this field represents

**Value Extraction Rules:**
- For currencies: Include the dollar sign and commas (e.g., "$1,250,000")
- For percentages: Include the % symbol (e.g., "5.25%")
- For dates: Use the format found in the document
- For square footage: Note if it's Rentable SF, Gross SF, or Net SF
- For per-unit metrics: Note if it's per unit, per SF, or annual/monthly

**Categorize fields into:** property_info, financial_metrics, rent_roll, unit_mix, market_data, loan_terms"""

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
            system_prompt = self._build_system_prompt_with_pdf_fields(stripped_fields)

            # Estimate and log token counts
            system_tokens = self._estimate_tokens(system_prompt)
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
                user_message = self._build_sheet_batch_user_message(sheet_batch_schema)

                # Estimate and log token counts for this batch
                user_tokens = self._estimate_tokens(user_message)
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
                message = await asyncio.to_thread(
                    self.client.messages.parse,
                    model=self.model,
                    max_tokens=settings.synthesis_llm_max_tokens,
                    temperature=0.0,
                    timeout=settings.synthesis_llm_timeout_seconds,
                    system=system_arg,
                    messages=[{"role": "user", "content": user_message}],
                    output_format=AutoMappingResult
                )

                # Log actual cache usage from Anthropic and accumulate totals
                usage = getattr(message, "usage", None)
                if usage is not None:
                    cache_creation = getattr(usage, "cache_creation_input_tokens", None) or 0
                    cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
                    input_tokens = getattr(usage, "input_tokens", None) or 0
                    output_tokens = getattr(usage, "output_tokens", None) or 0

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

            page_number = (
                (metadata.get("bbox", {}) or {}).get("page")
                or chunk.get("page_number")
                or metadata.get("page_number")
            )

            context.append({
                "text": chunk.get("text") or "",
                "page_number": page_number,
                "section_type": chunk.get("section_type") or metadata.get("chunk_type"),
            })

        return context

    def _estimate_tokens(self, text: str) -> int:
        """
        Rough token estimation (1 token ≈ 4 characters for English).
        For accurate counting, use tiktoken, but this is good enough for monitoring.
        """
        return len(text) // 4

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

    def _build_system_prompt_with_pdf_fields(self, pdf_fields: List[Dict[str, Any]]) -> str:
        """
        Build system prompt with instructions + ALL PDF fields (to be cached).

        This is sent once and cached. Excel sheets will be sent in the user message.
        """
        pdf_fields_json = json.dumps(pdf_fields, separators=(",", ":"), ensure_ascii=False)

        return f"""You are an expert real estate analyst mapping data fields from a PDF (Offering Memorandum) to cells in an Excel underwriting template.

You will receive batches of Excel sheets as user messages. Your job is to map the PDF fields below to those Excel sheets.

**PDF Fields (extracted from document):**

```json
{pdf_fields_json}
```

---

## Real Estate Terminology Reference (BIDIRECTIONAL)

**PURPOSE**: This table provides HIGH-CONFIDENCE matches for common abbreviations and equivalent terms.
**IMPORTANT**: This is an ADDED LAYER, not the only matching method. You should ALSO use semantic similarity for terms NOT listed here.

Terms in each row are EQUIVALENT. Match in EITHER direction. Case-insensitive.

### Pricing & Valuation
| Equivalent Terms (any ↔ any) |
|------------------------------|
| **Price, Listing Price, Asking Price, Sale Price, Offer Price, Purchase Price, Offering Price, Contract Price** |
| **Net Operating Income, NOI, Net Income, Operating Income, Annual NOI** |
| **Capitalization Rate, Cap Rate, Going-In Cap, Going In Cap Rate, In-Place Cap** |
| **Exit Cap Rate, Cap Rate at Refi, Refi Cap, Disposition Cap, Residual Cap, Terminal Cap** |
| **Price Per Unit, $/Unit, PPU, Cost Per Unit, Price/Unit** |
| **Price Per Square Foot, $/SF, PSF, Price/SF, Cost Per SF, Price Per SF, Price PSF** |

### Financing & Loan Terms
| Equivalent Terms (any ↔ any) |
|------------------------------|
| **Down Payment, Down Payment %, DP, DP%, Equity, Equity %, Cash Investment, Equity Contribution** |
| **Loan Amount, Debt, Mortgage Amount, Financing Amount, Loan, Senior Debt, Mortgage** |
| **Interest Rate, Rate, Int Rate, Note Rate, Loan Rate, Coupon, Mortgage Rate** |
| **Amortization, Amort, Amort Period, Amortization Period, Amortization Term, Amort (Mos), Amort (Yrs)** |
| **Interest-Only Period, I/O Period, I/O Mos, IO Months, IO, Interest Only, I/O, IO Period** |
| **Loan to Value, LTV, Loan-to-Value, L/V, Leverage** |
| **LTV at Refi, Loan to Value at Refi, Refi LTV, Exit LTV, Refinance LTV** |
| **Debt Service Coverage Ratio, DSCR, DCR, Debt Coverage, DSC, Debt Service Coverage** |
| **Debt Yield, DY, Debt Yield %, Yield on Debt** |
| **Loan Term, Term, Loan Period, Maturity** |

### Income & Expenses
| Equivalent Terms (any ↔ any) |
|------------------------------|
| **Gross Potential Rent, GPR, Scheduled Rent, Gross Scheduled Income, GSI, Potential Gross Income, PGI** |
| **Effective Gross Income, EGI, Gross Income, Total Income, Adjusted Gross Income** |
| **Operating Expenses, OpEx, Total Expenses, Expenses, Total Operating Expenses, Operating Costs** |
| **Vacancy, Vacancy Loss, Economic Vacancy, Physical Vacancy, Vacancy Rate, Vacancy %, V&C** |
| **Cash-on-Cash Return, CoC, Cash Yield, Cash Return, Cash on Cash, COC Return, CoC %** |
| **Internal Rate of Return, IRR, Levered IRR, Unlevered IRR, Project IRR, Investor IRR** |

### Investment Structure (LP/GP Waterfall)
| Equivalent Terms (any ↔ any) |
|------------------------------|
| **LP Split, Member Split, LP Share, Limited Partner Share, LP %, Investor Share, Member/LP Split** |
| **GP Split, Sponsor Split, GP Share, General Partner Share, GP %, Promote Share** |
| **Preferred Return, Pref, Pref Return, Hurdle, Hurdle Rate, Pref %, Preferred, Pref Return %** |
| **Pre Hurdle Split, Pre-Pref Split, Before Hurdle, Pre Hurdle Member/LP Split** |
| **Post Hurdle Split, Post-Pref Split, After Hurdle, Promote Split, Carried Interest, Promote** |
| **Equity Multiple, EM, Multiple, Return Multiple, Total Multiple, MOIC** |

### Property Metrics
| Equivalent Terms (any ↔ any) |
|------------------------------|
| **Square Feet, SF, SqFt, Sq. Ft., RSF, GSF, NRA, Rentable SF, Gross SF, Net Rentable Area, Total SF** |
| **Number of Units, Units, Unit Count, Total Units, # Units, # of Units, Unit #** |
| **Occupancy Rate, Occupancy, Occ., Physical Occupancy, Economic Occupancy, Occupancy %** |
| **Year Built, Built, Constructed, Construction Year, Yr Built, Year Constructed** |

### Rent Roll / Unit Data
| Equivalent Terms (any ↔ any) |
|------------------------------|
| **In-Place Rent, Current Rent, Actual Rent, Contract Rent, Existing Rent, Monthly Rent** |
| **Market Rent, Asking Rent, Proforma Rent, Pro Forma Rent, Projected Rent, Achievable Rent** |
| **Lease Expiration, Lease End, Expiry, Maturity Date, Lease Exp, End Date, Lease End Date** |
| **Unit Type, Bed/Bath, BR/BA, Floor Plan, Unit Mix, Bedroom Count, Floorplan** |

---

## Mapping Instructions

1. **Three-Layer Matching Strategy:**
   - **LAYER 1 (Highest Priority)**: Check the terminology table above. If a PDF field matches ANY term in a row, map to Excel cells with ANY equivalent term from that same row. Confidence: 0.95+
   - **LAYER 2 (Semantic Matching)**: For terms NOT in the table, use semantic similarity (e.g., "Property Address" → "Address", "Building Name" → "Prop Name"). Confidence: 0.75-0.94
   - **LAYER 3 (Context + Type)**: Consider data type compatibility and section context. A currency field in "Operating Statement" section likely maps to income/expense cells. Confidence: 0.50-0.74

2. **Confidence Score Guidelines:**
   - **0.95-1.0**: Exact match or terminology table match
   - **0.85-0.94**: Strong semantic match with same data type
   - **0.70-0.84**: Moderate match, terminology differs but meaning is clear
   - **0.50-0.69**: Weak match, may need user review
   - **0.10-0.49**: Low confidence, user should review
   - **Below 0.10**: Do NOT create mapping

3. **For each mapping, provide:**
   - `pdf_field_id`: ID of the PDF field
   - `pdf_field_name`: Name of the PDF field
   - `excel_cell`: Cell reference (e.g., "B2")
   - `excel_sheet`: Sheet name
   - `excel_label`: The label from Excel (for tables: "col_header (row_label)")
   - `confidence`: Confidence score (0.0-1.0)
   - `citations`: COPY the citations array from the PDF field exactly
   - `reasoning`: Brief explanation (e.g., "NOI maps to Net Operating Income - standard terminology")

4. **CRITICAL Matching Rules:**
   - Only create mappings with confidence >= 0.10
   - ALWAYS preserve the "citations" array from the PDF field
   - You MAY map the same PDF field to multiple Excel cells when those cells represent
     the same metric in different sections/summaries (e.g., dashboard rollups)
   - Do NOT map to cells that appear to be formula cells (calculated fields)
   - For currencies: Match currency fields to currency cells
   - For percentages: Match percentage fields to percentage cells
   - **Case-insensitive matching**: "ASKING PRICE" = "Asking Price" = "asking price"
   - **Partial match OK**: "Listing Price" matches "Price" if context is clear
   - **Abbreviation matching**: "I/O Mos" = "Interest-Only Period", "Amort" = "Amortization"

5. **CONCRETE MAPPING EXAMPLES:**

   **Example 1 - Terminology Table Match (0.95+ confidence):**
   - PDF field: `{{"name": "Listing Price", "extracted_value": "$2,500,000"}}`
   - Excel cell: `{{"cell": "C8", "label": "Asking Price", "type": "currency"}}`
   - Result: MAP with confidence 0.95 (terminology table: Price ↔ Asking Price)

   **Example 2 - Terminology Table Match (0.95+ confidence):**
   - PDF field: `{{"name": "Down Payment", "extracted_value": "35%"}}`
   - Excel cell: `{{"cell": "D10", "label": "Down Payment %", "type": "percentage"}}`
   - Result: MAP with confidence 0.98 (terminology table: Down Payment ↔ Down Payment %)

   **Example 3 - Abbreviation Match (0.95+ confidence):**
   - PDF field: `{{"name": "Interest Rate", "extracted_value": "6.50%"}}`
   - Excel cell: `{{"cell": "E12", "label": "Rate", "type": "percentage"}}`
   - Result: MAP with confidence 0.95 (terminology table: Interest Rate ↔ Rate)

   **Example 4 - Semantic Match (0.85 confidence):**
   - PDF field: `{{"name": "Property Address", "extracted_value": "123 Main St"}}`
   - Excel cell: `{{"cell": "B3", "label": "Address", "type": "text"}}`
   - Result: MAP with confidence 0.85 (semantic: Property Address → Address)

   **Example 5 - Investment Structure (0.95 confidence):**
   - PDF field: `{{"name": "LP Share", "extracted_value": "70%"}}`
   - Excel cell: `{{"cell": "F20", "label": "Pre Hurdle Member/LP Split", "type": "percentage"}}`
   - Result: MAP with confidence 0.95 (terminology table: LP Split ↔ Member/LP Split)

6. **Table Mapping Strategy:**
   - Match PDF rent roll data to Excel rent roll rows by unit number/type
   - Match PDF operating statement line items to Excel expense categories
   - Consider row_label AND col_header when matching table cells
   - If PDF has aggregated data (e.g., "Total Units"), map to summary rows, not detail rows

7. **Common Mapping Patterns:**
   - Operating Statement → Income/Expense section of Excel
   - Rent Roll → Unit detail table in Excel
   - Property Summary → Property Info section of Excel
   - Investment Highlights → Summary/Overview sheet
   - Loan Terms → Financing/Assumptions section of Excel
   - LP/GP Split → Waterfall or Returns section of Excel

8. **MAXIMIZE MAPPINGS:**
   - Your goal is to map as many PDF fields as possible to Excel cells
   - When in doubt about a match, create the mapping with appropriate confidence (0.50-0.70) rather than skipping
   - Users can review and reject incorrect mappings, but cannot create mappings you missed
   - Every unmapped field requires manual user work - minimize this burden"""

    def _build_sheet_batch_user_message(self, sheet_batch_schema: Dict[str, Any]) -> str:
        """
        Build user message with a batch of Excel sheets.

        Args:
            sheet_batch_schema: Schema containing a subset of sheets

        Returns:
            User message with sheet batch JSON
        """
        schema_json = json.dumps(sheet_batch_schema, separators=(",", ":"), ensure_ascii=False)

        total_kv = sheet_batch_schema.get("total_key_value_fields", 0)
        total_tables = sheet_batch_schema.get("total_tables", 0)
        sheet_names = [s.get("name") for s in sheet_batch_schema.get("sheets", [])]

        return f"""**Excel Template Sheets (batch of {len(sheet_names)}):**

Sheets in this batch: {", ".join(sheet_names)}
Total key-value fields: {total_kv}
Total tables: {total_tables}

**Excel Schema Structure:**

1. **Key-Value Fields** (in `key_value_fields` array):
    - Simple fillable cells with a nearby label
    - Example: {{"cell": "B2", "label": "Property Name", "type": "text"}}
    - Map PDF fields to these when the field name matches the label

2. **Table Cells** (in `tables[].fillable_cells` array):
    - Cells within structured tables
    - Have both `col_header` (column name) and optionally `row_label` (row name)
    - Example: {{"cell": "M28", "col_header": "Floor Plan", "row_label": "Unit 101", "type": "text"}}
    - Map PDF fields by considering BOTH the column header AND row context

```json
{schema_json}
```

Map the PDF fields (from system prompt) to the cells in these sheets."""

