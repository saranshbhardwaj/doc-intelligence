"""LLM service for template filling: field detection, auto-mapping, and data extraction.

Uses Anthropic's Structured Outputs feature to GUARANTEE valid JSON responses.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from anthropic import Anthropic
from pydantic import BaseModel, Field

from app.config import settings
from app.utils.logging import logger


# ============================================================================
# Pydantic Schemas for Structured Outputs
# ============================================================================

class DetectedField(BaseModel):
    """Schema for a single detected field from PDF."""
    name: str = Field(description="Clear, descriptive field name")
    type: str = Field(description="Data type: text, number, currency, percentage, date")
    sample_value: str = Field(description="Actual value found in the PDF")
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
            # Use Anthropic Structured Outputs (beta) - GUARANTEES valid JSON!
            message = await asyncio.to_thread(
                self.client.beta.messages.parse,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.0,
                timeout=settings.synthesis_llm_timeout_seconds,
                betas=["structured-outputs-2025-11-13"],  # Enable structured outputs
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

    def _format_chunks_with_citations(self, chunks: List[Dict[str, Any]]) -> str:
        """Format chunks with citation tokens for LLM consumption."""
        formatted_parts = []

        for i, chunk in enumerate(chunks):
            citation = chunk.get("citation", "[?]")
            text = chunk.get("text", "")
            page_num = chunk.get("page_number", 0)
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
  - Fields from "Financial Summary" → financial_metrics
  - Fields from "Property Details" → property_info

**PDF Content:**
{pdf_context}

**Instructions:**
1. Identify ALL structured data fields in the document:
   - **Property information** (name, address, type, year built, etc.) - often in Text chunks
   - **Financial metrics** (NOI, cap rate, price per SF, rental income, etc.) - often in Table chunks
   - **Size/capacity metrics** (SF, units, parking spaces, etc.) - both Text and Table chunks
   - **Tenant information** (names, lease terms, rent amounts, etc.) - often in Table chunks (rent rolls)
   - **Market data** (occupancy rate, market rent, comparable sales, etc.) - both chunk types

2. For each field, provide:
   - name: Clear, descriptive field name (use section heading for context if helpful)
   - type: Data type (text, number, currency, percentage, date)
   - sample_value: The actual value found in this PDF
   - confidence: Your confidence in the extraction (0.0-1.0)
   - citations: Array of citation tokens where this field was found
   - description: Brief explanation of what this field represents

3. **Leverage chunk metadata:**
   - For Table chunks: Extract ALL columns as fields (each column = separate field)
   - For Text chunks: Extract labeled key-value pairs
   - Use section headings to categorize fields logically

4. Categorize fields into logical groups (property_info, financial_metrics, tenant_data, etc.)

5. Focus on fields that are:
   - Clearly labeled or described in the document
   - Quantifiable or have specific values
   - Commonly used in real estate analysis
   - Likely to appear in Excel templates"""

    async def auto_map_fields(
        self,
        pdf_fields: List[Dict[str, Any]],
        excel_schema: Dict[str, Any],
        on_batch_complete=None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Automatically map PDF fields to Excel cells.

        Uses Anthropic's Structured Outputs to GUARANTEE valid JSON response.
        Processes in batches to avoid API timeouts for large datasets.

        Args:
            pdf_fields: List of detected PDF fields
            excel_schema: Excel template schema
            on_batch_complete: Optional callback(batch_num, total_batches, batch_mappings)

        Returns:
            {
                "mappings": [...],
                "total_mapped": 38,
                ...
            }
        """
        logger.info(f"Auto-mapping {len(pdf_fields)} PDF fields to Excel template (structured output)")

        # Batch size to avoid 10-minute API timeout
        BATCH_SIZE = 25

        # Strip unnecessary fields to reduce token usage (~26% reduction in user message)
        # Remove: description, source (not used by mapping logic)
        # Keep: id, name, type, sample_value, confidence, citations (all required for mapping)
        def strip_pdf_field(field: Dict[str, Any]) -> Dict[str, Any]:
            """Remove description and source fields to reduce tokens by ~26%."""
            return {
                "id": field.get("id"),
                "name": field.get("name"),
                "type": field.get("type"),
                "sample_value": field.get("sample_value"),
                "confidence": field.get("confidence"),
                "citations": field.get("citations", []),
            }

        try:
            system_prompt = self._build_auto_mapping_system_prompt(excel_schema)

            # Process in batches if we have many fields
            if len(pdf_fields) > BATCH_SIZE:
                logger.info(f"Processing {len(pdf_fields)} fields in batches of {BATCH_SIZE}")
                all_mappings = []
                total_high_confidence = 0
                total_batches = (len(pdf_fields) + BATCH_SIZE - 1) // BATCH_SIZE

                for i in range(0, len(pdf_fields), BATCH_SIZE):
                    batch = pdf_fields[i:i + BATCH_SIZE]
                    batch_num = (i // BATCH_SIZE) + 1

                    logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} fields)")

                    # Strip unnecessary fields before sending to LLM
                    stripped_batch = [strip_pdf_field(field) for field in batch]
                    user_message = self._build_auto_mapping_user_message(stripped_batch)

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
                        self.client.beta.messages.parse,
                        model=self.model,
                        max_tokens=settings.synthesis_llm_max_tokens,
                        temperature=0.0,
                        timeout=settings.synthesis_llm_timeout_seconds,
                        betas=["structured-outputs-2025-11-13"],
                        system=system_arg,
                        messages=[{"role": "user", "content": user_message}],
                        output_format=AutoMappingResult
                    )

                    usage = getattr(message, "usage", None)
                    if usage is not None:
                        cache_creation = getattr(usage, "cache_creation_input_tokens", None)
                        cache_read = getattr(usage, "cache_read_input_tokens", None)
                        input_tokens = getattr(usage, "input_tokens", None)
                        output_tokens = getattr(usage, "output_tokens", None)

                        # Some logger formats drop `extra=` fields; log a readable line too.
                        if cache_creation is not None or cache_read is not None:
                            logger.info(
                                f"Anthropic cache usage stats: cache_creation_input_tokens={cache_creation}, "
                                f"cache_read_input_tokens={cache_read}, input_tokens={input_tokens}, "
                                f"output_tokens={output_tokens}"
                            )

                    parsed_output = message.parsed_output
                    batch_result = parsed_output.model_dump()

                    # Collect mappings from this batch
                    batch_mappings = batch_result.get("mappings", [])
                    all_mappings.extend(batch_mappings)
                    total_high_confidence += batch_result.get("high_confidence_count", 0)

                    logger.info(
                        f"✅ Batch {batch_num}/{total_batches} complete: "
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
                    "high_confidence_count": total_high_confidence
                }

            else:
                # Single request for small datasets
                # Strip unnecessary fields before sending to LLM
                stripped_fields = [strip_pdf_field(field) for field in pdf_fields]
                user_message = self._build_auto_mapping_user_message(stripped_fields)

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

                message = await asyncio.to_thread(
                    self.client.beta.messages.parse,
                    model=self.model,
                    max_tokens=settings.synthesis_llm_max_tokens,
                    temperature=0.0,
                    timeout=settings.synthesis_llm_timeout_seconds,
                    betas=["structured-outputs-2025-11-13"],
                    system=system_arg,
                    messages=[{"role": "user", "content": user_message}],
                    output_format=AutoMappingResult
                )

                parsed_output = message.parsed_output
                result = parsed_output.model_dump()

            # Add status to all mappings
            for mapping in result.get("mappings", []):
                if "status" not in mapping:
                    mapping["status"] = "auto_mapped"

            logger.info(
                f"✅ Auto-mapped {result.get('total_mapped', 0)} fields "
                f"({result.get('high_confidence_count', 0)} high confidence)"
            )

            return result

        except Exception as e:
            logger.error(f"Error auto-mapping fields: {e}", exc_info=True)
            raise

    def _build_auto_mapping_system_prompt(self, excel_schema: Dict[str, Any]) -> str:
        """Build the *static* portion of the auto-mapping prompt.

        This is intended to be sent via the Anthropic `system` parameter with
        `cache_control: {type: 'ephemeral'}` so it can be reused across batches.
        """
        # Compact JSON to reduce tokens; caching makes this pay once per template per TTL.
        excel_schema_json = json.dumps(excel_schema, separators=(",", ":"), ensure_ascii=False)

        total_kv = excel_schema.get("total_key_value_fields", 0)
        total_tables = excel_schema.get("total_tables", 0)

        return f"""You are mapping data fields from a PDF to cells in an Excel template.

You will receive a batch of PDF fields as the user message. Your job is to map those PDF fields into the Excel schema below.

**Excel Template Schema:**
The Excel template has {total_kv} key-value fields and {total_tables} tables.

Schema structure:
- **key_value_fields**: Simple label-value pairs (e.g., "Property Name: [____]")
- **tables**: Structured tables with column headers and data rows (e.g., rent rolls, financial tables)

```json
{excel_schema_json}
```

**Excel Schema Structure Explained:**

1. **Key-Value Fields** (in `key_value_fields` array):
    - Simple fillable cells with a nearby label
    - Example: {{"cell": "B2", "label": "Property Name", "type": "text"}}
    - Map PDF fields to these when the field name matches the label

2. **Table Cells** (in `tables[].fillable_cells` array):
    - Cells within structured tables
    - Have both `col_header` (column name) and optionally `row_label` (row name)
    - Example: {{"cell": "M28", "col_header": "Floor Plan", "row_label": "Unit 101", "type": "text"}}
    - Map PDF fields by considering BOTH the column header AND row context

**Mapping Instructions:**

1. For each PDF field, find the best matching Excel cell based on:
    - **Semantic similarity** (e.g., "Property Name" → label "Prop. Name")
    - **Data type compatibility** (number fields → number cells)
    - **Context matching**:
      - For key-value fields: Match on `label`
      - For table cells: Match on combination of `col_header` and `row_label`
    - **Common real estate terminology** (NOI, Cap Rate, SF, etc.)

2. Assign a confidence score (0.0-1.0) for each mapping:
    - **0.95-1.0**: Exact or near-exact label match
    - **0.80-0.94**: Strong semantic match
    - **0.50-0.79**: Moderate match, may need user review
    - **Below 0.50**: Uncertain, leave unmapped

3. For each mapping, provide:
    - `pdf_field_id`: ID of the PDF field
    - `pdf_field_name`: Name of the PDF field
    - `excel_cell`: Cell reference (e.g., "B2")
    - `excel_sheet`: Sheet name
    - `excel_label`: For key-value fields: the label. For tables: "col_header (row_label)" format
    - `confidence`: Confidence score
    - `citations`: COPY the citations array from the PDF field
    - `reasoning`: Brief explanation of why this mapping was made

4. **CRITICAL Rules**:
    - Only create mappings with confidence >= 0.50
    - Preserve the "citations" array from the PDF field in every mapping
    - For table cells, set excel_label to describe both column and row (e.g., "Rent Amount (Unit 101)")
    - Avoid mapping the same PDF field to multiple Excel cells (choose the best match)

5. **Table Mapping Strategy**:
    - If a PDF field represents a single value, map to ONE table cell
    - If a PDF field could fill multiple rows (e.g., "Tenant List"), create separate mappings for each row
    - Consider the row_label context when mapping to table cells"""

    def _build_auto_mapping_user_message(self, pdf_fields: List[Dict[str, Any]]) -> str:
        """Build the *dynamic* per-batch user message for auto-mapping."""
        pdf_fields_json = json.dumps(pdf_fields, separators=(",", ":"), ensure_ascii=False)
        return f"""**PDF Fields (with citations):**
```json
{pdf_fields_json}
```"""

