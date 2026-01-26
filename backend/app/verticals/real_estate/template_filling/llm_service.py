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
- sample_value: The EXACT value found in the PDF (preserve original formatting)
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

                # Log actual cache usage from Anthropic
                usage = getattr(message, "usage", None)
                if usage is not None:
                    cache_creation = getattr(usage, "cache_creation_input_tokens", None)
                    cache_read = getattr(usage, "cache_read_input_tokens", None)
                    input_tokens = getattr(usage, "input_tokens", None)
                    output_tokens = getattr(usage, "output_tokens", None)

                    if cache_creation is not None or cache_read is not None:
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
                "high_confidence_count": total_high_confidence
            }

            # Add status to all mappings
            for mapping in result.get("mappings", []):
                if "status" not in mapping:
                    mapping["status"] = "auto_mapped"

            logger.info(
                f"\n✅ Auto-mapping complete: {result.get('total_mapped', 0)} total mappings across "
                f"{total_sheets} sheets ({result.get('high_confidence_count', 0)} high confidence, "
                f"{result.get('total_unmapped', 0)} unmapped)"
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
        Keeps: id, name, type, sample_value, confidence, citations (all required)
        """
        return {
            "id": field.get("id"),
            "name": field.get("name"),
            "type": field.get("type"),
            "sample_value": field.get("sample_value"),
            "confidence": field.get("confidence"),
            "citations": field.get("citations", []),
        }

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
   - **Below 0.50**: Do NOT create mapping

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
   - Only create mappings with confidence >= 0.50
   - ALWAYS preserve the "citations" array from the PDF field
   - Do NOT map the same PDF field to multiple Excel cells (choose best match)
   - Do NOT map to cells that appear to be formula cells (calculated fields)
   - For currencies: Match currency fields to currency cells
   - For percentages: Match percentage fields to percentage cells
   - **Case-insensitive matching**: "ASKING PRICE" = "Asking Price" = "asking price"
   - **Partial match OK**: "Listing Price" matches "Price" if context is clear
   - **Abbreviation matching**: "I/O Mos" = "Interest-Only Period", "Amort" = "Amortization"

5. **CONCRETE MAPPING EXAMPLES:**

   **Example 1 - Terminology Table Match (0.95+ confidence):**
   - PDF field: `{{"name": "Listing Price", "sample_value": "$2,500,000"}}`
   - Excel cell: `{{"cell": "C8", "label": "Asking Price", "type": "currency"}}`
   - Result: MAP with confidence 0.95 (terminology table: Price ↔ Asking Price)

   **Example 2 - Terminology Table Match (0.95+ confidence):**
   - PDF field: `{{"name": "Down Payment", "sample_value": "35%"}}`
   - Excel cell: `{{"cell": "D10", "label": "Down Payment %", "type": "percentage"}}`
   - Result: MAP with confidence 0.98 (terminology table: Down Payment ↔ Down Payment %)

   **Example 3 - Abbreviation Match (0.95+ confidence):**
   - PDF field: `{{"name": "Interest Rate", "sample_value": "6.50%"}}`
   - Excel cell: `{{"cell": "E12", "label": "Rate", "type": "percentage"}}`
   - Result: MAP with confidence 0.95 (terminology table: Interest Rate ↔ Rate)

   **Example 4 - Semantic Match (0.85 confidence):**
   - PDF field: `{{"name": "Property Address", "sample_value": "123 Main St"}}`
   - Excel cell: `{{"cell": "B3", "label": "Address", "type": "text"}}`
   - Result: MAP with confidence 0.85 (semantic: Property Address → Address)

   **Example 5 - Investment Structure (0.95 confidence):**
   - PDF field: `{{"name": "LP Share", "sample_value": "70%"}}`
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

