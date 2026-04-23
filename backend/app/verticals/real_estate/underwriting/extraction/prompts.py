"""Extraction prompts for Self Storage underwriting.

Three system prompts (100% static, cacheable with Anthropic ephemeral cache):
1. OM_EXTRACTION_SYSTEM_PROMPT — Offering Memorandum extraction
2. RENT_ROLL_EXTRACTION_SYSTEM_PROMPT — Rent Roll extraction
3. T12_EXTRACTION_SYSTEM_PROMPT — Trailing-12-Month operating statement extraction
"""

OM_EXTRACTION_SYSTEM_PROMPT = """You are an expert CRE analyst extracting structured financial data from an Offering Memorandum (OM).

CRITICAL RULES:
1. Extract ONLY data explicitly present in the document — never infer or calculate
2. Return null/None for missing fields — do not guess
3. Numbers: return as floats, remove all formatting ($, commas, %), e.g. "$1,234,567" → 1234567.0
4. Percentages: return as decimals, e.g. "95%" → 0.95
5. Include confidence scores (0.0-1.0) for each major field: explicit text = 0.8+, inferred = lower
6. Page references help with traceability
7. Distinguish stated vs. broker pro forma assumptions

EXTRACT (as JSON):
- Property: name, address, asset_type (always "self_storage"), num_units, rentable_sqft, year_built
- Income basis: income_basis_months (int, 6 or 12) when the document states income is based on
  trailing N months (e.g. "trailing 6-month income, annualized"); income_basis_note (str) for any
  accompanying explanation. Return null for both when not stated.
- Value-add evidence (extract only when explicitly stated, never infer):
    - physical_occupancy_pct: stated occupancy percentage as decimal (e.g. "91% occupancy" → 0.91)
    - price_per_rentable_sqft: stated price per rentable square foot if the OM lists it
    - below_market_tenant_pct: share of tenants paying below street rate as decimal
      (e.g. "36 percent of tenants are below street rate" → 0.36)
    - below_market_monthly_variance: total monthly rent gap in dollars across all below-market tenants
      (e.g. "monthly variance of $868" → 868.0)
    - below_market_annual_upside: annualized dollar upside from raising below-market tenants to street
      rate (e.g. "$10,410 annually" → 10410.0)
    - value_add_notes: free-text summary of any explicitly stated expansion or value-add opportunities
      such as unit conversions, remote management, or rent growth initiatives. ≤200 chars.
    - noi_projected: projected net operating income if explicitly stated
- Market context / demographics when explicitly stated: nearby_storage_count_1mi, nearby_storage_count_3mi, nearby_storage_count_5mi, population_3mi, avg_household_income_3mi, storage_sqft_per_capita_3mi
- Acquisition: purchase_price (asking), closing_cost_pct if stated, capex_reserve_per_unit if stated, market_cap_rate_purchase if stated
- Income: gross_potential_rent_annual (stated), avg_in_place_rent_per_unit_monthly, avg_market_rent_per_unit_monthly, stated occupancy_pct, other_income_annual if stated, rent_growth_pct if stated
- Expenses (extract from the operating statement table when present):
    Prefer the "Year 1" or "Year-One" column for all line items.
    Use "Current" column only when Year 1 is absent.
    Never use the "Pro Forma" column for base-case expense inputs.
    Extract each line item as an annual dollar amount (remove $ and commas):
    - expense_office_admin_annual: "Office & Administrative"
    - expense_bank_fees_annual: "Bank & Credit Card Fees"
    - expense_contract_services_annual: "Contract Services (Fire, Security & Grounds)"
    - expense_miscellaneous_annual: "Miscellaneous"
    - expense_utilities_annual: "Utilities & Trash"
    - expense_telephone_annual: "Telephone & Communications"
    - expense_marketing_annual: "Marketing & Promotion"
    - expense_repairs_maintenance_annual: "Repairs, Maintenance & Reserves"
    - expense_insurance_annual: "Property Insurance"
    - expense_payroll_annual: "Salaries, Taxes & Benefits (On-Site)"
    - expense_property_tax_annual: "Property Taxes"
    - expense_mgmt_fee_annual: "Third Party Management (Off-Site)"
    - expense_total_annual: "Total Operating Expenses"
    - noi_year_one_stated: "Net Operating Income" from Year 1 column
    - noi_current_stated: "Net Operating Income" from Current column
    - expense_ratio_pro_forma: "Expenses % EGI" — prefer Year 1 value
- Financing: loan_amount, interest_rate, loan_term_years, amortization_years, loan_type if stated
- Exit: hold_period_years, exit_cap_rate, selling_cost_pct, market_cap_rate_sale if stated
- Broker metrics: broker_cap_rate, broker_noi if stated
- Unit mix: when a unit-mix overview table is present, extract one row per size/type bucket with section, unit_type, size, standard_sqft, num_units, occupied_units, occupancy_pct, current_rent, market_rent if explicitly separate, rent_per_sqft, potential_rent, occupied_sqft, total_sqft, pct_of_total_sqft
- Rent comps: when the OM includes a competitive set or nearby facility rent table, extract one row per facility/size bucket with facility, size, asking_rent, rent_per_sqft, distance_mi, and notes for address, year built, square footage, missing data, or specials
- Never collapse multiple size buckets into one rent_comps row. If a facility lists 5 x 10, 10 x 10, 10 x 15, and 10 x 20, emit four separate rows repeating the same facility, distance, and notes.
- The size field must contain exactly one size bucket such as "10 x 10". Never place comma-separated sizes, addresses, year built, or square footage in size.
- Map Rent/Unit into asking_rent and Rent/Sq.Ft. into rent_per_sqft whenever those columns are present.
- Distinguish cap-rate labels carefully:
    - "Current Cap Rate", "In-Place Cap Rate", "Going-In Cap Rate", and cap rate stated at the asking or purchase basis map to market_cap_rate_purchase.
    - "Pro Forma Cap Rate", "Stabilized Cap Rate", "Exit Cap Rate", "Going-Out Cap Rate", and "Terminal Cap Rate" map to exit_cap_rate.
    - Never map "Current Cap Rate" into exit_cap_rate.
- Distinguish tax-rate labels carefully:
    - "Mill Rate", "Current Tax Rate", "Tax Rate", "Mill Levy", and similar property-tax rate labels map to mil_rate.
    - Extract the stated rate value exactly as shown after numeric normalization; do not confuse it with annual property tax expense or property tax growth.

Return as valid JSON only. No explanations."""

RENT_ROLL_EXTRACTION_SYSTEM_PROMPT = """You are an expert CRE analyst extracting lease data from a Rent Roll.

CRITICAL RULES:
1. Extract ONLY explicit data — never estimate
2. Return null/None for missing fields
3. Numbers: floats, no formatting
4. Dates: ISO format YYYY-MM-DD
5. Vacant units: monthly_rent = 0.0
6. Calculate: total_occupied_units, total_monthly_rent, occupancy_pct = occupied / total

EXTRACT (as JSON):
- Summary: total_units, occupied_units, occupancy_pct, total_monthly_rent, annual_gross_potential_rent, avg_in_place_rent_per_unit_monthly, avg_market_rent_per_unit_monthly when a market column exists, avg_rent_per_sqft
- Unit mix: when a unit-type summary or occupancy-by-size table is present, extract one row per bucket with section, unit_type, size, standard_sqft, num_units, occupied_units, occupancy_pct, current_rent, market_rent if explicitly separate, rent_per_sqft, potential_rent, occupied_sqft, total_sqft, pct_of_total_sqft
- Leases: array of {tenant_name (or unit_id if unnamed), unit_id, unit_size_sqft, monthly_rent, lease_start (YYYY-MM-DD), lease_end (YYYY-MM-DD), confidence, page}

Return as valid JSON only. No explanations."""

T12_EXTRACTION_SYSTEM_PROMPT = """You are an expert CRE analyst extracting financial data from a 12-month operating statement.

CRITICAL RULES:
1. Extract ONLY actual historical data — no projections
2. Return null/None for missing categories
3. Numbers: floats, no formatting
4. All amounts should be annual totals
5. Flag unusual one-time items (capital improvements, legal settlements, etc.)
6. Calculate: total_revenue, total_opex, implied_noi, opex_ratio = total_opex / total_revenue

EXTRACT (as JSON):
- Revenue: rental_income, late_fees, other_income (itemized), bad_debt_annual if stated, corrections_collections_annual if stated, total_revenue
- Expenses: property_tax, insurance, mgmt_fee, payroll, repairs_maintenance, utilities, marketing, other_opex (itemized), total_opex
- Summary: total_revenue, total_opex, noi, expense_ratio_actual, unusual_items

Return as valid JSON only. No explanations."""


def create_om_user_prompt(document_text: str) -> str:
    """Wrap document text for OM extraction."""
    return f"""Extract underwriting data from this Offering Memorandum:

{document_text}

Return extracted data as JSON."""


def create_rent_roll_user_prompt(document_text: str) -> str:
    """Wrap document text for Rent Roll extraction."""
    return f"""Extract lease data from this Rent Roll:

{document_text}

Return extracted data as JSON."""


def create_t12_user_prompt(document_text: str) -> str:
    """Wrap document text for T12 operating statement extraction."""
    return f"""Extract financial data from this 12-month operating statement:

{document_text}

Return extracted data as JSON."""


# ── Phase 1: Schema-agnostic condensation (map step) ─────────────────────────

PHASE1_CONDENSATION_SYSTEM_PROMPT = """You are extracting financially relevant data from real estate document chunks.

Extract every financial figure, property metric, and deal term you find.
Return raw values only — no calculations, no inference.

CHUNK TYPES (indicated in each chunk header):
- KV Pair: Highest confidence — data is already structured. Extract exactly as shown.
- Table Chunk: High confidence — extract every numeric column and row.
- Narrative: Extract only explicitly stated figures (e.g. "$485,000 annual rent"). Skip vague descriptions.

CITATION: Each chunk starts with a token like [S1:p5]. Use that exact token in citations.

NUMBERS: Remove $, commas. Convert percentages to decimals. "$1,234,567" → "1234567". "95%" → "0.95".

Return ONLY valid JSON, no markdown:
{
  "fields": [
    {
      "field": "descriptive_field_name",
      "value": "numeric_or_text_value",
      "citations": ["[S1:p5]"],
      "source_text": "brief snippet"
    }
  ]
}"""


def create_phase1_user_prompt(chunk_context: str) -> str:
    return f"""Extract all financially relevant data from these document chunks:

{chunk_context}

Return JSON only."""


# ── Phase 2: Schema-fitting (reduce step) per doc type ───────────────────────

import json as _json


def _schema_json(fields: list[dict]) -> str:
    return _json.dumps({f["name"]: f.get("type", "float | null") for f in fields}, indent=2)


_OM_FIELDS = [
    {"name": "name", "type": "str | null"},
    {"name": "address", "type": "str | null"},
    {"name": "purchase_price", "type": "float | null"},
    {"name": "closing_cost_pct", "type": "float | null (decimal, e.g. 0.02)"},
    {"name": "market_cap_rate_purchase", "type": "float | null (decimal, e.g. 0.0625)"},
    {"name": "capex_reserve_per_unit", "type": "float | null"},
    {"name": "num_units", "type": "int | null"},
    {"name": "rentable_sqft", "type": "float | null"},
    {"name": "year_built", "type": "int | null"},
    {"name": "nearby_storage_count_1mi", "type": "int | null"},
    {"name": "nearby_storage_count_3mi", "type": "int | null"},
    {"name": "nearby_storage_count_5mi", "type": "int | null"},
    {"name": "population_3mi", "type": "int | null"},
    {"name": "avg_household_income_3mi", "type": "float | null"},
    {"name": "storage_sqft_per_capita_3mi", "type": "float | null"},
    {"name": "gpr_annual_projected", "type": "float | null (annual)"},
    {"name": "avg_in_place_rent_per_unit_monthly", "type": "float | null (monthly)"},
    {"name": "avg_market_rent_per_unit_monthly", "type": "float | null (monthly)"},
    {"name": "vacancy_pct_projected", "type": "float | null (decimal, e.g. 0.08)"},
    {"name": "expense_ratio_pro_forma", "type": "float | null (decimal)"},
    {"name": "other_income_annual", "type": "float | null (annual)"},
    {"name": "rent_growth_pct", "type": "float | null (decimal)"},
    {"name": "noi_projected", "type": "float | null (annual)"},
    {"name": "mgmt_fee_pct", "type": "float | null (decimal)"},
    {"name": "opex_growth_pct", "type": "float | null (decimal)"},
    {"name": "property_tax_growth_pct", "type": "float | null (decimal)"},
    {"name": "mil_rate", "type": "float | null"},
    {"name": "exit_cap_rate", "type": "float | null (decimal, e.g. 0.065)"},
    {"name": "market_cap_rate_sale", "type": "float | null (decimal, e.g. 0.0675)"},
    {"name": "hold_period_years", "type": "int | null"},
    {"name": "selling_cost_pct", "type": "float | null (decimal)"},
    {"name": "target_irr", "type": "float | null (decimal)"},
    {"name": "target_cash_on_cash", "type": "float | null (decimal)"},
    {"name": "target_equity_multiple", "type": "float | null"},
    {"name": "ltv_pct", "type": "float | null (decimal, e.g. 0.70)"},
    {"name": "interest_rate_pct", "type": "float | null (decimal, e.g. 0.065)"},
    {"name": "amortization_years", "type": "int | null"},
    {"name": "loan_term_years", "type": "int | null"},
    {"name": "unit_mix", "type": "array of {section, unit_type, size, standard_sqft, num_units, occupied_units, occupancy_pct, current_rent, market_rent, rent_per_sqft, potential_rent, occupied_sqft, total_sqft, pct_of_total_sqft, climate_type (\"CC\"|\"NC\"|\"UNKNOWN\"), unit_category (\"storage\"|\"parking\"|\"residential\"|\"office\"|\"other\")}"},
    {"name": "rent_comps", "type": "array of {facility, size, asking_rent, rent_per_sqft, distance_mi, notes}"},

    {"name": "income_basis_months", "type": "int | null (6 or 12, when stated)"},
    {"name": "income_basis_note", "type": "str | null"},

    {"name": "physical_occupancy_pct", "type": "float | null (decimal, stated in OM)"},
    {"name": "price_per_rentable_sqft", "type": "float | null (stated in OM if present)"},
    {"name": "below_market_tenant_pct", "type": "float | null (decimal, e.g. 0.36)"},
    {"name": "below_market_monthly_variance", "type": "float | null (monthly dollar gap)"},
    {"name": "below_market_annual_upside", "type": "float | null (annual dollar upside)"},
    {"name": "value_add_notes", "type": "str | null (free text expansion/upside narrative)"},

    # Individual OM expense line items (Year 1 column preferred per scenario rule)
    {"name": "expense_office_admin_annual",       "type": "float | null"},
    {"name": "expense_bank_fees_annual",          "type": "float | null"},
    {"name": "expense_contract_services_annual",  "type": "float | null"},
    {"name": "expense_miscellaneous_annual",      "type": "float | null"},
    {"name": "expense_utilities_annual",          "type": "float | null"},
    {"name": "expense_telephone_annual",          "type": "float | null"},
    {"name": "expense_marketing_annual",          "type": "float | null"},
    {"name": "expense_repairs_maintenance_annual","type": "float | null"},
    {"name": "expense_insurance_annual",          "type": "float | null"},
    {"name": "expense_payroll_annual",            "type": "float | null"},
    {"name": "expense_property_tax_annual",       "type": "float | null"},
    {"name": "expense_mgmt_fee_annual",           "type": "float | null"},
    {"name": "expense_total_annual",              "type": "float | null"},
    {"name": "noi_year_one_stated",               "type": "float | null (Year 1 column NOI)"},
    {"name": "noi_current_stated",                "type": "float | null (Current column NOI)"}
]

_T12_FIELDS = [
    {"name": "gpr_annual_actual", "type": "float | null (annualised if T-6)"},
    {"name": "vacancy_credit_loss_pct_actual", "type": "float | null (decimal)"},
    {"name": "expense_ratio_actual", "type": "float | null (decimal)"},
    {"name": "other_income_annual", "type": "float | null"},
    {"name": "bad_debt_annual", "type": "float | null"},
    {"name": "corrections_collections_annual", "type": "float | null"},
    {"name": "property_tax_annual", "type": "float | null"},
    {"name": "insurance_annual", "type": "float | null"},
    {"name": "mgmt_fee_pct_actual", "type": "float | null (decimal)"},
    {"name": "payroll_annual", "type": "float | null"},
    {"name": "repairs_maintenance_annual", "type": "float | null"},
    {"name": "utilities_annual", "type": "float | null"},
    {"name": "marketing_annual", "type": "float | null"},
    {"name": "other_opex_annual", "type": "float | null"},
    {"name": "noi_actual", "type": "float | null"},
    {"name": "period_months", "type": "int | null (12 or 6)"},
]

_RENT_ROLL_FIELDS = [
    {"name": "num_units_actual", "type": "int | null"},
    {"name": "physical_occupancy_pct", "type": "float | null (decimal)"},
    {"name": "avg_in_place_rent_per_unit_monthly", "type": "float | null (monthly)"},
    {"name": "avg_market_rent_per_unit_monthly", "type": "float | null (monthly)"},
    {"name": "rent_growth_pct", "type": "float | null (decimal, if stated)"},
    {"name": "unit_mix", "type": "array of {section, unit_type, size, standard_sqft, num_units, occupied_units, occupancy_pct, current_rent, market_rent, rent_per_sqft, potential_rent, occupied_sqft, total_sqft, pct_of_total_sqft, climate_type (\"CC\"|\"NC\"|\"UNKNOWN\"), unit_category (\"storage\"|\"parking\"|\"residential\"|\"office\"|\"other\")}"},
    {"name": "lease_records", "type": "array of {unit_id, monthly_rent, lease_expiration (YYYY-MM-DD), sqft}"},
]


def _phase2_system(doc_label: str, fields: list[dict], condensed_json: str) -> str:
    return f"""You are converting condensed field extractions into a typed {doc_label} underwriting schema.

The condensed data below was extracted from a real estate document.
Map field values to the schema. Rules:
- Monetary values: float, no symbols or commas
- Percentages: decimal (0.065 not 6.5%)
- "purchase price", "asking price", "listing price" → purchase_price
- "current cap rate", "in-place cap rate", "going-in cap rate", and cap rate stated at the asking or purchase basis → market_cap_rate_purchase
- "pro forma cap rate", "stabilized cap rate", "exit cap", "going-out cap", "terminal cap" → exit_cap_rate
- "mill rate", "current tax rate", "tax rate", and "mill levy" → mil_rate
- "gross potential rent", "GPR", "scheduled rent" → gpr_annual_projected (annualised)
- "hold period", "investment horizon" → hold_period_years
- Do not map annual property tax expense or property tax growth into mil_rate
- Nearby competitor / facility counts can map into nearby_storage_count_1mi, nearby_storage_count_3mi, nearby_storage_count_5mi
- Market demographics can map into population_3mi, avg_household_income_3mi, and storage_sqft_per_capita_3mi when explicitly tied to the property market area
- For OM unit-mix tables, preserve one row per bucket. Use the section header (for example NON-CLIMATE or COVERED PARKING) in both section and unit_type when no more specific type label exists.
- For OM competitive-set rent tables, preserve one row per facility and size bucket in rent_comps. Use asking_rent for Rent/Unit, rent_per_sqft for Rent/Sq.Ft., and keep notes for address, year built, square footage, blanks like "no data", or specials.
- Never collapse multiple size buckets into one rent_comps row. Repeat facility, distance, and notes across separate rows when a facility lists multiple sizes.
- The size field must contain exactly one size bucket. Do not put comma-separated sizes, addresses, year built, or square footage into size.
- If the table shows Rent/Unit and Rent/Sq.Ft., populate asking_rent and rent_per_sqft for each emitted row.
- For rent-roll unit-mix or occupancy summary tables, preserve one row per size/type bucket using the same unit_mix row structure as the OM output.
- In unit_mix rows, map weighted average or stated asking monthly rate into current_rent unless a separate market rate is explicitly shown.
- When a document contains multiple scenarios (e.g. Current, Year-One, Pro Forma):
  prefer the "Year-One" or "Year 1" column for gpr_annual_projected, 
  vacancy_pct_projected, noi_projected, and expense line items.
  Use the "Current" column only when Year-One is absent.
  Never use the "Pro Forma" column for base-case inputs.
- When multiple "other income" sub-categories are present (admin fees, late fees,
  tenant insurance, miscellaneous), sum them into other_income_annual rather than
  picking one. Cite all contributing source tokens.
- For OM expense line items, always prefer the Year 1 column dollar amounts.
  Map ALL operating expenses to one of the 7 primary fields: expense_property_tax_annual,
  expense_insurance_annual, expense_payroll_annual, expense_repairs_maintenance_annual,
  expense_utilities_annual, expense_marketing_annual, expense_mgmt_fee_annual.
  Any expense that does not clearly fit one of those 7 — including but not limited to
  bank fees, office/admin supplies, telephone/communications, contract services, janitorial,
  security monitoring, credit card processing, miscellaneous — should be extracted into the
  most appropriate named field if one exists (expense_bank_fees_annual,
  expense_contract_services_annual, expense_office_admin_annual, expense_telephone_annual,
  expense_miscellaneous_annual). If no named field matches, treat it as part of
  other_opex_annual. Never leave an expense line item unaccounted for.
  Never map the expense ratio percentage into any dollar field.
- For unit_mix rows, set climate_type to "CC" if the row is described as climate-controlled,
  temperature-controlled, heated, or humidity-controlled. Set it to "NC" if described as
  non-climate, drive-up, outdoor, or similar. Set it to "UNKNOWN" if unclear.
  Set unit_category to "storage" for standard storage units, "parking" for parking spaces
  (covered or uncovered), "residential" for apartments or dwelling units, "office" for
  office space, and "other" for anything else.
- If a value genuinely cannot be found, return null

CITATIONS: For every SCALAR field you populate (not arrays like unit_mix, rent_comps, or lease_records), also emit the companion citation fields:
- {{field}}_confidence: your confidence 0.0-1.0
- {{field}}_citations: the [S{{n}}:p{{page}}] tokens from condensed_fields that contained this data (e.g. ["S1:p5"])
- {{field}}_source: verbatim snippet ≤40 chars — the key phrase only, no full sentences

Condensed data:
{condensed_json}

Return ONLY valid JSON matching this schema (null for missing):
{_schema_json(fields)}"""


def create_phase2_om_prompt(condensed_json: str) -> str:
    return _phase2_system("Offering Memorandum (OM)", _OM_FIELDS, condensed_json)


def create_phase2_t12_prompt(condensed_json: str) -> str:
    return _phase2_system("T-12/T-6 Operating Statement", _T12_FIELDS, condensed_json)


def create_phase2_rent_roll_prompt(condensed_json: str) -> str:
    return _phase2_system("Rent Roll", _RENT_ROLL_FIELDS, condensed_json)
