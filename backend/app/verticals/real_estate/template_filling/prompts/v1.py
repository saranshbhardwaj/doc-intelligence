"""V1 prompt set — extracted from the original llm_service.py hardcoded prompts.

Includes all Pydantic response models coupled to these prompts.
"""

import json
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field, field_validator

from app.verticals.real_estate.template_filling.source_map import (
    STRUCTURE_HIGH_CONFIDENCE,
    STRUCTURE_LOW_CONFIDENCE,
    trim_om_structure_for_prompt,
)

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
    citations: List[str] = Field(description="Citation tokens where field was found (e.g., ['[S1:p2]'])")
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
    citations: List[str] = Field(default_factory=list, description="Citation tokens like [S1:p5]")
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
    citations: List[str] = Field(default_factory=list, description="Citation tokens like [S1:p5]")
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


class OMStructureKey(BaseModel):
    """One detected structure key with confidence and source support."""

    present: bool = Field(description="Whether this key/section is present in the OM")
    label: Optional[str] = Field(None, description="Detected OM label/header, when applicable")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this structure key")
    citations: List[str] = Field(default_factory=list, description="Citation tokens like [S1:p5]")
    evidence: Optional[str] = Field(None, description="Short evidence quote or explanation")


class OMColumnMap(BaseModel):
    """Operating-statement column map."""

    current: OMStructureKey = Field(description="Current or in-place operating column")
    t12: OMStructureKey = Field(description="Trailing 12 month actuals operating column")
    year1: OMStructureKey = Field(description="Year 1 or underwriting operating column")
    pro_forma: OMStructureKey = Field(description="Pro forma operating column")
    stabilized: OMStructureKey = Field(description="Stabilized operating column")


class OMSectionPresence(BaseModel):
    """Section-routing flags for template extraction."""

    current_operating_statement_present: OMStructureKey
    year1_operating_statement_present: OMStructureKey
    pro_forma_operating_statement_present: OMStructureKey
    t12_present: OMStructureKey
    unit_mix_present: OMStructureKey
    rent_roll_present: OMStructureKey
    rent_comps_present: OMStructureKey
    market_summary_present: OMStructureKey


class OMStructureDetectionResult(BaseModel):
    """Source Map for a real estate OM."""

    column_map: OMColumnMap
    section_presence: OMSectionPresence


# ============================================================================
# V1 Prompt Set
# ============================================================================


class V1PromptSet(PromptSet):
    version = "v1"

    def build_detect_om_structure(self, pdf_fields_json: str) -> PromptPair:
        system_prompt = (
            "You are detecting the document structure of a real estate offering memorandum "
            "before extracting values into an analyst Excel model.\n\n"
            "Use the Azure Document Intelligence data below. Return structure only; do not "
            "extract cell values.\n\n"
            f"```json\n{pdf_fields_json}\n```"
        )
        user_message = (
            "Detect the OM Source Map with two artifacts: `column_map` and `section_presence`.\n\n"
            "`column_map` must identify operating-statement period columns: current, t12, "
            "year1, pro_forma, and stabilized. For each key return present, label, confidence, "
            "citations, and evidence. Evidence should quote or summarize the page/table header "
            "that supports the key.\n\n"
            "`section_presence` must identify routing flags: "
            "current_operating_statement_present, year1_operating_statement_present, "
            "pro_forma_operating_statement_present, t12_present, unit_mix_present, "
            "rent_roll_present, rent_comps_present, market_summary_present. For each flag "
            "return present, label, confidence, citations, and evidence.\n\n"
            f"Confidence policy: use >={STRUCTURE_HIGH_CONFIDENCE:.2f} for clear table headers "
            f"or explicit section titles; {STRUCTURE_LOW_CONFIDENCE:.2f}-"
            f"{STRUCTURE_HIGH_CONFIDENCE - 0.01:.2f} for likely but ambiguous evidence; "
            f"<{STRUCTURE_LOW_CONFIDENCE:.2f} when uncertain. Use citations like [S1:p5] "
            "from the input data.\n\n"
            "Return ONLY JSON matching the response schema."
        )
        return PromptPair(
            system_prompt=system_prompt,
            user_message=user_message,
            response_model=OMStructureDetectionResult,
        )

    # -- Stage 2: schema field extraction ----------------------------------

    def build_extract_schema_fields(
        self,
        pdf_fields_json: str,
        unmapped_fields: List[Dict[str, Any]],
        om_structure: Optional[Dict[str, Any]] = None,
    ) -> PromptPair:
        structure_context = ""
        if om_structure:
            prompt_structure = trim_om_structure_for_prompt(om_structure)
            structure_context = (
                "\n\nDetected OM Source Map to respect during extraction:\n"
                f"```json\n{json.dumps(prompt_structure, indent=2)}\n```"
            )
        system_prompt = (
            "You are extracting values from a real estate PDF for specific named schema fields.\n\n"
            "Below is the complete list of key-value pairs, full tables, and market context "
            "(narratives) extracted by Azure Document Intelligence:\n"
            f"```json\n{pdf_fields_json}\n```\n\n"
            f"{structure_context}\n\n"
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
                "sheet": f.get("sheet"),
                "value_cell": f.get("value_cell"),
                "label_cell": f.get("label_cell"),
                "aliases": f.get("pdf_aliases", []),
                "data_type": f.get("data_type", "text"),
                "description": f.get("description"),
                "extraction_rule": f.get("extraction_rule"),
                "source_period": f.get("source_period"),
                "source_basis": f.get("source_basis"),
                "fill_when": f.get("fill_when"),
                "requires_structure": f.get("requires_structure", []),
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
            '      "citations": ["[S1:p3]"],\n'
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
            "- Provide citations like [S1:p15] and reasoning per row.\n"
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
            '          "citations": ["[S1:p15]"],\n'
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


    # -- Stage 1: field detection ------------------------------------------

    def build_detect_fields(self, pdf_context: str) -> PromptPair:
        user_message = f"""You are analyzing a Real Estate offering memorandum (OM) or property document to extract all structured data fields.

Your task is to identify every piece of structured information that could be extracted and used to fill an Excel template.

**CRITICAL: Citation Format**
Each chunk in the PDF content is prefixed with a citation token like [S1:p5] (Source 1, Page 5).
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
            "- Provide citations like [S1:p5] and a brief reasoning per row (reasoning is required).\n"
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
            '          "citations": ["[S1:p15]"],\n'
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
