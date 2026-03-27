"""V1 prompt set — extracted from the original llm_service.py hardcoded prompts.

Includes all Pydantic response models coupled to these prompts.
"""

import json
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field, field_validator

from .base import PromptPair, PromptSet


# ============================================================================
# Pydantic response models (coupled to v1 prompts)
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
    reasoning: Optional[str] = Field(
        None,
        description="AI reasoning for this extraction (e.g., 'Found in KV pair', 'Extracted from Table X, column Y')",
    )


class SchemaFieldExtractionResult(BaseModel):
    """Result of Stage 2 targeted schema field extraction."""

    results: List[SchemaFieldResult] = Field(description="Results for each requested schema field")
    total_found: int = Field(description="Number of fields with non-null values found")
    total_not_found: int = Field(description="Number of fields not found in PDF")


class SchemaTableRowResult(BaseModel):
    """Extraction result for a single table row in a YAML schema table."""

    row_index: int = Field(description="0-based row index within the schema table data range")
    row_label: Optional[str] = Field(
        None, description="Row label if provided (matches Excel row identifier column)"
    )
    values: Dict[str, Optional[str]] = Field(
        description=(
            "Map of excel_column -> extracted value. "
            "MUST include all columns from the schema. "
            "Use null only if genuinely not found."
        )
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence for this row")
    citations: List[str] = Field(default_factory=list, description="Citation tokens like [D1:p5]")
    reasoning: Optional[str] = Field(
        None,
        description="AI reasoning for this row extraction (e.g., 'Matched row label', 'Extracted from Table X with column mapping')",
    )

    @field_validator("values", mode="before")
    @classmethod
    def coerce_values_to_str(cls, v: Any) -> Dict[str, Optional[str]]:
        if not isinstance(v, dict):
            return v
        return {k: str(val) if val is not None else None for k, val in v.items()}


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
# V1 Prompt Set
# ============================================================================


class V1PromptSet(PromptSet):
    version = "v1"

    # -- Stage 2: schema field extraction ----------------------------------

    def build_extract_schema_fields(
        self,
        pdf_fields_json: str,
        unmapped_fields: List[Dict[str, Any]],
    ) -> PromptPair:
        system_prompt = (
            "You are extracting values from a real estate PDF for specific named schema fields.\n\n"
            "Below is the complete list of key-value pairs, full tables, and market context "
            "(narratives) extracted by Azure Document Intelligence:\n"
            f"```json\n{pdf_fields_json}\n```\n\n"
            "For each requested schema field, find its value from the Azure DI data above.\n"
            "Match by the field's aliases and semantic meaning. For example:\n"
            '- A field with aliases ["City", "Location City"] might appear as "City:", "Location:", "Property City", etc.\n'
            '- A field with aliases ["Asking Price", "Purchase Price"] might appear as "List Price", "Sale Price", etc.\n\n'
            "Be aggressive in matching — if a value is semantically equivalent to an alias, extract it.\n"
            "Return null only if the value genuinely cannot be found anywhere in the PDF data."
        )

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

        return PromptPair(
            system_prompt=system_prompt,
            user_message=user_message,
            response_model=SchemaFieldExtractionResult,
        )

    # -- Stage 2: schema table extraction via RAG --------------------------

    def build_extract_table_values_rag(
        self,
        context_json: str,
        table_requests: List[Dict[str, Any]],
        header_equivalents: str,
    ) -> PromptPair:
        system_prompt = (
            "You are extracting table values from a real estate PDF for multiple YAML schema tables.\n\n"
            "You are given a small, high-signal set of retrieved chunks (tables + key-value pairs).\n"
            "Use ONLY this context to extract values. Do not guess.\n\n"
            "Retrieved context:\n"
            f"```json\n{context_json}\n```\n\n"
            f"{header_equivalents}\n"
        )

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

        return PromptPair(
            system_prompt=system_prompt,
            user_message=user_message,
            response_model=SchemaTableExtractionResult,
        )

    # -- Stage 3: generic auto-mapping ------------------------------------

    def build_auto_map_system(self, pdf_fields_json: str) -> str:
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

    def build_auto_map_user(self, sheet_batch_schema: Dict[str, Any]) -> str:
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

    def get_auto_map_response_model(self) -> Type[BaseModel]:
        return AutoMappingResult

    # -- Stage 1: field detection ------------------------------------------

    def build_detect_fields(self, pdf_context: str) -> PromptPair:
        user_message = f"""You are analyzing a Real Estate offering memorandum (OM) or property document to extract all structured data fields.

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

        return PromptPair(
            system_prompt="",
            user_message=user_message,
            response_model=FieldDetectionResult,
        )

    # -- Stage 2: single-table RAG extraction ------------------------------

    _TABLE_HEADER_EQUIVALENTS = """Table header equivalences (case-insensitive):
- Type, Unit Type, Unit, Floor Plan
- # Units, Units, Unit Count, Count
- Sqft, Sq Ft, Sq.Ft., Square Feet, SF
- Sq.Ft./Unit, SF/Unit, Size, Area
- Rent/Unit, Rent, Monthly Rent, Asking Rent
- Rent/Sq Ft, Rent/Sq.Ft., Rent per Sq Ft, $/SF
"""

    def build_extract_table_values_rag_single(
        self,
        context_json: str,
        table_request: Dict[str, Any],
    ) -> PromptPair:
        system_prompt = (
            "You are extracting table values from a real estate PDF for a single YAML schema table.\n\n"
            "You are given a small, high-signal set of retrieved chunks (tables + key-value pairs).\n"
            "Use ONLY this context to extract values. Do not guess.\n\n"
            "Retrieved context:\n"
            f"```json\n{context_json}\n```\n\n"
            f"{self._TABLE_HEADER_EQUIVALENTS}"
        )

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

        return PromptPair(
            system_prompt=system_prompt,
            user_message=user_message,
            response_model=SchemaTableExtractionResult,
        )
