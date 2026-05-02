"""Extraction prompts for Self Storage underwriting.

Three system prompts (100% static, cacheable with Anthropic ephemeral cache):
1. OM_EXTRACTION_SYSTEM_PROMPT — Offering Memorandum extraction
2. RENT_ROLL_EXTRACTION_SYSTEM_PROMPT — Rent Roll extraction
3. T12_EXTRACTION_SYSTEM_PROMPT — Trailing-12-Month operating statement extraction
"""

import json as _json

OM_EXTRACTION_SYSTEM_PROMPT = """You are an expert CRE analyst extracting structured financial data from an Offering Memorandum (OM).

CRITICAL RULES:
1. If your confidence in a field is below ~60%, omit the field. Never estimate.
2. Extract ONLY data explicitly present in the document — never infer or calculate
3. Omit missing fields — do not guess or emit null placeholders
4. Numbers: return as floats, remove all formatting ($, commas, %), e.g. "$1,234,567" → 1234567.0
5. Percentages: return as decimals, e.g. "95%" → 0.95
6. Include confidence scores (0.0-1.0) for each major field: explicit text = 0.8+, inferred = lower
7. Page references help with traceability
8. Distinguish stated vs. broker pro forma assumptions

EXTRACT (as JSON):
- Property: name, address, asset_type (always "self_storage"), num_units, rentable_sqft, year_built
- Income basis: income_basis_months (int, 6 or 12) when the document states income is based on
  trailing N months (e.g. "trailing 6-month income, annualized"); income_basis_note (str) for any
  accompanying explanation. Omit both when not stated.
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
- Market context / demographics (extract from any demographics, market overview, or competition section of the OM — these often appear on a separate page):
    - nearby_storage_count_1mi: integer count of competing facilities within 1 mile. "No Competitors within 1-Mile" → 0
    - nearby_storage_count_3mi: integer count of competing facilities within 3 miles. Count distinct facilities listed in any rent-comp or competition table if an explicit count is not stated
    - nearby_storage_count_5mi: integer count within 5 miles if explicitly stated
    - population_3mi: total population within 3-mile radius as stated. Radius tables vary by
      document — match the column whose header is closest to 3 miles:
        • "1 Mile | 3 Miles | 5 Miles" → use the "3 Miles" column (middle). Example row
          "2023 Estimate 10,509 63,110 153,689" → population_3mi = 63,110.
        • "1 Mile | 2 Miles | 3 Miles" → use the "3 Miles" column (last).
        • "3 Miles | 5 Miles" → use the "3 Miles" column (first).
        • "1 Mile | 5 Miles" (no 3-mile column) → omit population_3mi.
        • Single-radius tables (e.g. "3-Mile Radius" header) → use that value directly.
      Always match by column header, not by picking the largest or middle value.
      Do not use Population Age 25+, Housing Units, or Occupied Units rows for population_3mi.
    - avg_household_income_3mi: average household income within the 3-mile trade area as a float
      (e.g. "average household income … is $65,499" → 65,499.0). Apply the same radius-column
      matching rules above. Use the 3-mile figure ONLY — do NOT use metro, MSA, submarket, or
      city-level income figures even if they appear nearby. If the OM shows a demographics table
      with multiple radii (1/3/5 mi), always pick the 3-mile column for this field.
    - storage_sqft_per_capita_3mi: square feet of storage per capita within 3 miles if stated. Apply the same radius-column matching rules above.
- Acquisition: purchase_price (asking), closing_cost_pct if stated, capex_reserve_per_unit if stated, market_cap_rate_purchase if stated
- Income (extract from the YEAR 1 column when a multi-column operating statement is present;
  fall back to Current column only when Year 1 is absent):
    - gross_potential_rent_annual: Year 1 Gross Potential Rent (annualised)
    - avg_in_place_rent_per_unit_monthly: average monthly in-place rent per unit ONLY if the OM
      states it as a single explicit aggregate figure (e.g. "Average In-Place Rent: $125/unit/mo"
      or "Avg Monthly Rent Per Unit: $114"). Do NOT compute or derive this from individual unit-mix
      rows — omit if not explicitly stated as an aggregate
    - avg_market_rent_per_unit_monthly: average market rent per unit if explicitly stated; omit otherwise
    - vacancy_pct_projected: Year 1 total economic vacancy as a decimal. Economic vacancy combines
      physical vacancy AND rent concessions/bad debt. Look in the YEAR 1 column for a row labeled
      "(Economic Vacancy)", "(Vacancy)", or "(Physical Vacancy) + (Rent Concessions/Bad Debt)".
      If shown as "12.78% / ($36,530)", return 0.1278. Omit if not found — never default.
    - other_income_annual: Sum of ALL non-rental income items in the Year 1 column. In self-storage
      OMs this typically includes: Administrative Fees, Late/Lien/NSF Fees, Tenant Insurance Net
      Commissions, and Miscellaneous Income. This equals the difference between "Effective Gross
      Income" and "Effective Gross Rental Income" in the operating statement. Extract the aggregate
      AND the individual components when present:
        - other_income_admin_fees_annual: "Administrative Fees" Year 1
        - other_income_late_fees_annual: "Late, Lien, NSF Fees" (or "Late Fees") Year 1
        - other_income_insurance_annual: "Tenant Insurance Net Commissions" Year 1
        - other_income_misc_annual: "Miscellaneous Income" Year 1
    - rent_growth_pct: annual rent growth assumption if stated
- Expenses (extract from the operating statement table when present):
    Prefer the "Year 1" or "Year-One" column for all line items.
    Use "Current" column only when Year 1 is absent.
    Never use the "Pro Forma" column for base-case expense inputs.
    Extract each line item as an annual dollar amount (remove $ and commas):
    - expense_office_admin_annual: "Office & Administrative"
    - expense_bank_fees_annual: "Bank & Credit Card Fees"
    - expense_contract_services_annual: "Contract Services (Fire, Security & Grounds)"
    - expense_miscellaneous_annual: "Miscellaneous"
    - expense_telephone_annual: "Telephone & Communications"
    - expense_payroll_annual: "Salaries, Taxes & Benefits (On-Site)"
    - STEP 1 — DETECT STRUCTURE: Before extracting any expense values, fill these fields:
        detected_deal_subtype: "stabilized" (existing ops, Year-1 has post-sale adjustments
          like tax reassessment) | "value_add" (owner-operated Current with $0 management/
          payroll/marketing; Year-1 adds professional management costs) | "unsupported"
          (ground-up development, non-self-storage, or unclear).
        detected_current_column_label: exact column header for current operations —
          "Current", a calendar year ("2024", "2023"), or a phrase ("2024 Financials",
          "2023 Actuals", "Trailing 12"). Null if no current column exists.
        detected_year1_column_label: exact column header for Year-1 projections —
          "Year 1", "Year-One", "Year 1 Projected". Null if absent.
        detected_has_current_column: true if a current-operations column exists
          alongside Year-1, false otherwise.
        detected_expense_format: "absolute" if expense line items are dollar totals;
          "per_sqft" if shown as $/sqft (you must multiply by rentable_sqft to produce
          the annual dollar total); "mixed" if both formats appear.
        detected_income_period_label: period the current column covers as written —
          "T-12", "T-6", "2024 Actuals", "Trailing 12". Null if not stated.
    - STEP 2 — EXTRACT using your detected labels as anchors. For each of the five
      adjustable expense line items, read _current from detected_current_column_label
      and _year1 from detected_year1_column_label:
        • If detected_has_current_column is false: emit only _year1 fields; omit _current.
        • If detected_expense_format is "per_sqft": multiply rate × rentable_sqft first.
        • When Current is explicitly $0 (owner-operated): emit _current=0.0 — never omit it.
        • Never emit only one of the pair when both columns exist. If Year-1 and Current
          are identical, still emit both.
        • For tables with more than 3 columns (Year 2, Year 3 ...): ignore beyond Year-1.
        • If detected_deal_subtype is "unsupported": return only the six detected_* fields.
      - expense_property_tax_annual_year1 / expense_property_tax_annual_current:
          "Property Taxes". Extract the dollar amount directly from each column —
          do not compute from assessed value or tax rate.
      - expense_insurance_annual_year1 / expense_insurance_annual_current:
          "Property Insurance".
      - expense_repairs_maintenance_annual_year1 / expense_repairs_maintenance_annual_current:
          "Repairs, Maintenance & Reserves".
      - expense_marketing_annual_year1 / expense_marketing_annual_current:
          "Marketing & Promotion".
      - expense_utilities_annual_year1 / expense_utilities_annual_current:
          "Utilities & Trash".
    - expense_mgmt_fee_annual: "Third Party Management (Off-Site)"
    - expense_total_annual: "Total Operating Expenses"
    - noi_year_one_stated: "Net Operating Income" from Year 1 column
    - noi_current_stated: "Net Operating Income" from Current column
    - expense_ratio_pro_forma: "Expenses % EGI" — prefer Year 1 value
    - mgmt_fee_pct: if the OM explicitly states the management fee as a percentage in text
      (e.g. "Third Party Management: 5% of GPR" or "Management Fee: 8%"), extract as decimal
      (0.05). Do NOT compute from expense_mgmt_fee_annual ÷ revenue. Only extract when a
      percentage is explicitly stated in text.
    - property_tax_growth_pct: ONLY when the OM states a property-tax-specific annual growth
      rate separate from general opex growth (e.g. "property taxes grow 4% annually, other
      expenses grow 2%"). If only one blended opex growth rate applies to all expenses,
      omit this field — do not copy opex_growth_pct into this field.
    - Property-tax calculation mechanics, extract only when explicitly stated:
      - property_tax_value_basis_amount: fair cash value, appraised value, assessed market
        value, or purchase-price tax basis explicitly used in a tax calculation.
      - property_tax_assessed_value: assessed value or taxable assessed value after the
        assessment ratio is applied.
      - property_tax_assessment_ratio: assessment ratio as a decimal, e.g. 11% -> 0.11.
      - property_tax_millage_rate: true mills per $1,000 of assessed value. Example:
        "111.61 mills" or "$111.61 per $1,000 assessed value" -> property_tax_millage_rate = 111.61.
      - property_tax_rate_per_assessed_dollar: tax rate per $1 of assessed value. Example:
        "current tax rate ($0.11161)" or "$0.11161 per assessed dollar" -> property_tax_rate_per_assessed_dollar = 0.11161.
      If the tax-rate unit is ambiguous, omit both tax-rate fields rather than guessing.
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
- Distinguish property-tax mechanics carefully:
    - "Mill Rate", "Mill Levy", "millage", or "$X per $1,000 assessed value" map to property_tax_millage_rate.
    - "Current Tax Rate", "Tax Rate", or "$X per assessed dollar" map to property_tax_rate_per_assessed_dollar only when the unit is clear.
    - Example: "Y2 has been calculated using the current tax rate ($0.11161)" -> property_tax_rate_per_assessed_dollar = 0.11161.
    - Example: "111.61 mills" -> property_tax_millage_rate = 111.61.
    - Do not confuse tax rate with annual property tax expense, property tax growth, assessed value, appraised value, or assessment ratio.
    - If the same note also lists appraised value, assessed value, assessment ratio, or tax bill, extract those into their own fields only when explicitly labeled.

EXAMPLE OUTPUT (partial — missing fields omitted for brevity):
{
  "purchase_price": 4750000.0,
  "num_units": 312,
  "gpr_annual_projected": 485000.0,
  "vacancy_pct_projected": 0.1278,
  "other_income_annual": 18400.0,
  "other_income_insurance_annual": 12000.0,
  "other_income_late_fees_annual": 6400.0,
  "unit_mix": [
    {"section": "Non-Climate", "unit_type": "Non-Climate", "size": "10 x 10", "standard_sqft": 100, "num_units": 48, "occupied_units": 44, "occupancy_pct": 0.917, "current_rent": 89.0, "market_rent": 95.0, "climate_type": "NC", "unit_category": "storage"},
    {"section": "Non-Climate", "unit_type": "Non-Climate", "size": "10 x 20", "standard_sqft": 200, "num_units": 24, "occupied_units": 21, "occupancy_pct": 0.875, "current_rent": 149.0, "market_rent": 159.0, "climate_type": "NC", "unit_category": "storage"}
  ],
  "rent_comps": [
    {"facility": "StoreSmart Dallas", "size": "10 x 10", "asking_rent": 99.0, "rent_per_sqft": 0.99, "distance_mi": 0.8, "climate_type": "NC", "standard_sqft": 100, "notes": "2018 build, drive-up"},
    {"facility": "StoreSmart Dallas", "size": "10 x 20", "asking_rent": 169.0, "rent_per_sqft": 0.845, "distance_mi": 0.8, "climate_type": "NC", "standard_sqft": 200, "notes": "2018 build, drive-up"}
  ]
}

Return as valid JSON only. No explanations."""

RENT_ROLL_EXTRACTION_SYSTEM_PROMPT = """You are an expert CRE analyst extracting lease data from a self-storage rent roll.

CRITICAL RULES:
1. If your confidence in a field is below ~60%, omit the field. Never estimate.
2. Extract only explicit source data and mechanical row math from visible rows. Never estimate.
3. Omit missing fields — do not guess or emit null placeholders.
4. Numbers: floats, no $ or commas. Percentages: decimals (0.91, not 91%).
5. Dates: ISO format YYYY-MM-DD when an actual date is shown.
6. Include occupied and vacant units when row-level unit data is present.
7. Vacant units: monthly_rent = 0.0 and lease_expiration = null.

SUMMARY SCALARS:
- num_units_actual: total unit count, including occupied and vacant units.
- physical_occupancy_pct: occupied units / total units as a decimal. Compute from visible
  occupied/vacant counts when no stated occupancy percentage is available.
- avg_in_place_rent_per_unit_monthly: sum of occupied current monthly rents / occupied unit count.
  Use a stated aggregate only when clearly labeled as in-place or current rent.
  Do not average market rents into this field.
- avg_market_rent_per_unit_monthly: average market/street/asking monthly rent when a market-rate
  column exists. Omit when no market-rate column or aggregate exists.
- rent_growth_pct: annual rent growth or rent increase as a decimal only if explicitly stated.

UNIT MIX:
When a unit-type summary, occupancy-by-size table, or row-level unit list is present, extract one
row per size/type bucket:
- section: source section label, such as "Climate Controlled", "Non-Climate", "Parking".
- unit_type: more specific type if shown; otherwise repeat section.
- size: exactly one size bucket such as "5 x 10", "10 x 10", or "10 x 20".
- standard_sqft: numeric area in square feet, e.g. 10 x 10 -> 100.
- num_units: total units in the bucket.
- occupied_units: occupied units in the bucket.
- occupancy_pct: occupied_units / num_units as a decimal.
- current_rent: weighted average monthly in-place rent per occupied unit for the bucket.
- market_rent: weighted average monthly market/street rent for the bucket, if shown.
- rent_per_sqft: current_rent / standard_sqft.
- potential_rent: market_rent * num_units when market_rent exists; otherwise current_rent * num_units.
- occupied_sqft: occupied_units * standard_sqft.
- total_sqft: num_units * standard_sqft.
- pct_of_total_sqft: total_sqft / property rentable sqft when total rentable sqft is available.
- climate_type: "CC" for climate-controlled, temperature-controlled, heated, or humidity-controlled;
  "NC" for non-climate, drive-up, outdoor, or unconditioned; "UNKNOWN" if unclear.
- unit_category: "storage" for standard storage, "parking" for parking/RV/boat/vehicle spaces,
  "residential" for apartments or dwelling units, "office" for office, "other" otherwise.

LEASE RECORDS:
Extract one record per unit when row-level unit data is present:
- unit_id: unit identifier or unit number.
- monthly_rent: current monthly rent; 0.0 for vacant units.
- lease_expiration: lease end / expiration date as YYYY-MM-DD. Omit for vacant or month-to-month.
- sqft: unit square footage.

EXAMPLE OUTPUT (partial — missing fields omitted for brevity):
{
  "num_units_actual": 312,
  "physical_occupancy_pct": 0.891,
  "avg_in_place_rent_per_unit_monthly": 97.40,
  "unit_mix": [
    {"section": "Climate Controlled", "unit_type": "Climate Controlled", "size": "5 x 10", "standard_sqft": 50, "num_units": 30, "occupied_units": 27, "occupancy_pct": 0.9, "current_rent": 79.0, "market_rent": 85.0, "climate_type": "CC", "unit_category": "storage"},
    {"section": "Climate Controlled", "unit_type": "Climate Controlled", "size": "10 x 10", "standard_sqft": 100, "num_units": 40, "occupied_units": 35, "occupancy_pct": 0.875, "current_rent": 109.0, "market_rent": 119.0, "climate_type": "CC", "unit_category": "storage"}
  ],
  "lease_records": [
    {"unit_id": "CC-101", "monthly_rent": 109.0, "lease_expiration": "2025-09-30", "sqft": 100},
    {"unit_id": "CC-102", "monthly_rent": 0.0, "sqft": 100}
  ]
}

Return as valid JSON only. No explanations."""

T12_EXTRACTION_SYSTEM_PROMPT = """You are an expert CRE analyst extracting actual historical financial data from a self-storage T-12, T-6, YTD, or operating statement.

CRITICAL RULES:
1. If your confidence in a field is below ~60%, omit the field. Never estimate.
2. Extract only actual historical operating data. Do not use broker projections or pro forma figures.
3. Omit missing categories. Do not estimate missing values or emit null placeholders.
4. Numbers: floats, no $ or commas. Percentages: decimals (0.08, not 8%).
5. Return totals for the source statement period. Do not annualize T-6 or YTD values before returning.
6. Set period_months to the number of months covered. The merger annualizes using 12 / period_months.
7. Mechanical math is allowed only from visible rows/columns, such as summing monthly columns when a
   total column is blank or absent.

PERIOD DETECTION:
- Look for date ranges and month columns. Jan-Dec = 12 months; Jul-Dec = 6 months.
- If the statement says T-12, trailing twelve, or shows 12 month columns, set period_months = 12.
- If it says T-6 or shows 6 month columns, set period_months = 6.
- If it is YTD, set period_months to the visible month count.
- If the period cannot be determined, omit period_months rather than guessing.

COLUMN LAYOUT:
- T-12 statements often show one row per category and one column per month plus a Total column.
- Prefer the Total column for the statement period when populated.
- If the Total column is blank or missing, sum the visible monthly columns for that row.
- Some statements show one row per month and one column per category. In that layout, sum each
  category down the visible monthly rows.
- Prefer the most recent operating period when multiple periods are shown.

REVENUE:
- gpr_annual_actual: Gross Potential Rent, Scheduled Rent, Gross Rental Income, Rental Income, or
  tenant rental revenue for the statement period.
- vacancy_credit_loss_pct_actual: vacancy, concessions, credit loss, bad debt, or write-offs as a
  decimal when shown as a percentage. If only dollar lines are shown, compute percentage only when
  GPR is also visible.
- other_income_annual: all non-rental income for the statement period, including admin fees, late
  fees, tenant insurance commissions, move-in fees, lien/NSF fees, truck rental, retail/locks,
  merchandise, and miscellaneous income.
- bad_debt_annual: bad debt, write-offs, uncollectible rent, or delinquency write-off when broken out.
- corrections_collections_annual: collections, corrections, prior-period adjustments, or similar.

EXPENSES:
- property_tax_annual: Property Taxes, Real Estate Taxes, Tax Expense.
- insurance_annual: Property Insurance, Casualty Insurance, Hazard Insurance.
- mgmt_fee_pct_actual: explicit management fee percentage only. If management fee is a dollar line,
  include it in other_opex_annual and omit mgmt_fee_pct_actual.
- payroll_annual: Payroll, Salaries & Wages, Labor, Benefits, Taxes & Benefits, On-Site Manager.
- repairs_maintenance_annual: Repairs & Maintenance, R&M, Maintenance, Janitorial, Cleaning,
  Landscaping, Snow Removal, Pest Control.
- utilities_annual: Utilities, Electric, Gas, Water, Trash, Sewer.
- marketing_annual: Marketing, Advertising, Promotion, Online Marketing, SEO, Web Leads.
- other_opex_annual: operating expenses not mapped above, including Office Supplies, Bank Fees,
  Credit Card Fees, Merchant Fees, Software, SiteLink, storEDGE, Telephone, Communications,
  Security Monitoring, Gate/Fire, Legal & Professional, Administrative, Owner Auto, Travel,
  Meals, Miscellaneous, and dollar management fees.

SUMMARY:
- noi_actual: Net Operating Income, NOI, or Net Income from Operations when stated. If no NOI line is
  stated, compute only when total revenue and total operating expenses are visible.
- expense_ratio_actual: total operating expenses / effective gross income as a decimal when stated
  or mechanically derivable from visible totals.
- period_months: integer month count for the source statement period.

EXAMPLE OUTPUT (partial — missing fields omitted for brevity):
{
  "gpr_annual_actual": 242000.0,
  "other_income_annual": 18600.0,
  "property_tax_annual": 14200.0,
  "insurance_annual": 3800.0,
  "payroll_annual": 28500.0,
  "utilities_annual": 6100.0,
  "repairs_maintenance_annual": 4200.0,
  "marketing_annual": 3600.0,
  "noi_actual": 139600.0,
  "expense_ratio_actual": 0.532,
  "period_months": 12
}

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

MULTI-COLUMN TABLES: When a table row has values across multiple columns
(e.g. Current | Year 1 | Pro Forma, or 2024 Actuals | Year 1 Projected | Year 2):
- Extract a SEPARATE field entry for each column's value for expense line items.
- Suffix the field name with a normalized column label:
    {"field": "property_taxes_current", "value": "6139", "citations": [...], "source_text": "..."}
    {"field": "property_taxes_year1",   "value": "15346", "citations": [...], "source_text": "..."}
    {"field": "insurance_current",      "value": "9867",  "citations": [...], "source_text": "..."}
    {"field": "insurance_year1",        "value": "11840", "citations": [...], "source_text": "..."}
- Never collapse multiple columns into one field entry.
- When a column value is explicitly $0, emit value="0" — do NOT skip it.

STRUCTURE METADATA: When an operating statement table is present, also emit these
metadata fields (one entry each, not per-row):
  {"field": "operating_statement_column_structure",
   "value": "Current | Year 1 | Pro Forma",
   "citations": ["[S1:p5]"], "source_text": "column headers from operating statement"}
  {"field": "expense_format",
   "value": "absolute",
   "citations": ["[S1:p5]"], "source_text": "expense line items are dollar totals"}
  (set value to "per_sqft" when expenses appear as $/sqft rates, "mixed" when both)
  {"field": "income_period_label",
   "value": "T-12",
   "citations": ["[S1:p5]"], "source_text": "trailing 12 months"}
  (use the exact label from the document: "T-12", "T-6", "2024 Actuals", "Trailing 12", etc.)

CITATION: Each chunk starts with a source token like [S1:p5] for PDFs or [S1:Rent Roll!R2-R201] for spreadsheets. Use that exact token in citations.

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

def _schema_json(fields: list[dict]) -> str:
    return _json.dumps({f["name"]: f.get("type", "float | null") for f in fields}, indent=2)


# Derived from extraction model field metadata — do not edit manually.
# To add a new scalar field: add it to the corresponding model in schemas.py
# with Field(description=..., json_schema_extra={"cite": bool}).
from .schemas import _OM_REGISTRY as _om_reg, _T12_REGISTRY as _t12_reg, _RENT_ROLL_REGISTRY as _rr_reg  # noqa: E402

_OM_FIELDS = _om_reg["om_fields_for_prompt"] + [
    {
        "name": "unit_mix",
        "type": (
            'array of {section, unit_type, size, standard_sqft, num_units, occupied_units, '
            'occupancy_pct, current_rent, market_rent, rent_per_sqft, potential_rent, '
            'occupied_sqft, total_sqft, pct_of_total_sqft, '
            'climate_type ("CC"|"NC"|"UNKNOWN"), '
            'unit_category ("storage"|"parking"|"residential"|"office"|"other")}'
        ),
    },
    {
        "name": "rent_comps",
        "type": (
            'array of {facility, size, asking_rent, rent_per_sqft, distance_mi, '
            'climate_type ("CC"|"NC"|"UNKNOWN"), standard_sqft (float|null), notes}'
        ),
    },
]

# T-12 scalar fields derived from T12Extraction registry; no complex fields to append.
_T12_FIELDS = _t12_reg["t12_fields_for_prompt"]

_RENT_ROLL_FIELDS = _rr_reg["rr_fields_for_prompt"] + [
    {"name": "unit_mix", "type": "array of {section, unit_type, size, standard_sqft, num_units, occupied_units, occupancy_pct, current_rent, market_rent, rent_per_sqft, potential_rent, occupied_sqft, total_sqft, pct_of_total_sqft, climate_type (\"CC\"|\"NC\"|\"UNKNOWN\"), unit_category (\"storage\"|\"parking\"|\"residential\"|\"office\"|\"other\")}"},
    {"name": "lease_records", "type": "array of {unit_id, monthly_rent (0.0 for vacant), lease_expiration (YYYY-MM-DD or null), sqft}"},
]


_OM_PHASE2_RULES = """OM MAPPING RULES:
- "purchase price", "asking price", "listing price" -> purchase_price
- "current cap rate", "in-place cap rate", "going-in cap rate", and cap rate stated at the asking or purchase basis -> market_cap_rate_purchase
- "pro forma cap rate", "stabilized cap rate", "exit cap", "going-out cap", "terminal cap" -> exit_cap_rate
- "mill rate", "mill levy", "millage", and "$X per $1,000 assessed value" -> property_tax_millage_rate
- "current tax rate", "tax rate", and "$X per assessed dollar" -> property_tax_rate_per_assessed_dollar only when the unit is clear
- Property-tax assumptions and footnotes can support explicit tax mechanics. Example: "Y2 has been calculated using the current tax rate ($0.11161)" -> property_tax_rate_per_assessed_dollar = 0.11161
- "111.61 mills" -> property_tax_millage_rate = 111.61
- If the tax-rate unit is ambiguous, omit both tax-rate fields rather than guessing
- "gross potential rent", "GPR", "scheduled rent" -> gpr_annual_projected (annual)
- "hold period", "investment horizon" -> hold_period_years
- Do not map annual property tax expense, property tax growth, appraised value, assessed value, or assessment ratio into tax-rate fields
- Nearby competitor / facility counts -> nearby_storage_count_1mi, nearby_storage_count_3mi, nearby_storage_count_5mi. "No Competitors within 1-Mile" -> nearby_storage_count_1mi = 0. Count distinct facilities in rent-comp tables for nearby_storage_count_3mi if not explicitly stated
- Population within 3 miles -> population_3mi (integer). Average household income within 3 miles -> avg_household_income_3mi (float). Square feet per capita -> storage_sqft_per_capita_3mi. Extract these even when they appear on a demographics or market overview page separate from the operating statement. For all *_3mi fields, match by the column whose header is closest to 3 miles — do not pick the largest or middle value blindly. "1 Mile | 3 Miles | 5 Miles" → middle column; "1 Mile | 2 Miles | 3 Miles" → last column; "3 Miles | 5 Miles" → first column; "1 Mile | 5 Miles" → omit; single-radius table with 3-mile header → use directly. Example: "2023 Estimate 10,509 63,110 153,689" in a 1/3/5 table → population_3mi = 63,110. Do not use age-25+, housing-unit, or occupied-unit rows for population_3mi.
- For OM unit-mix tables, preserve one row per bucket. Use the section header (for example NON-CLIMATE or COVERED PARKING) in both section and unit_type when no more specific type label exists.
- For OM competitive-set rent tables, preserve one row per facility and size bucket in rent_comps. Use asking_rent for Rent/Unit, rent_per_sqft for Rent/Sq.Ft., and keep notes for address, year built, square footage, blanks like "no data", or specials.
- Never collapse multiple size buckets into one rent_comps row. Repeat facility, distance, and notes across separate rows when a facility lists multiple sizes.
- The size field must contain exactly one size bucket. Do not put comma-separated sizes, addresses, year built, or square footage into size.
- If the table shows Rent/Unit and Rent/Sq.Ft., populate asking_rent and rent_per_sqft for each emitted row.
- For each rent_comps row, set climate_type to "CC" if the facility or unit is described as climate-controlled, temperature-controlled, heated, or humidity-controlled; "NC" if described as non-climate, drive-up, or outdoor; "UNKNOWN" if unclear. Set standard_sqft to the numeric area in sqft derived from size (e.g. "5x10" -> 50, "10x20" -> 200).
- Phase 1 condensation extracted both column values for expense line items using
  _current and _year1 suffixes (e.g. property_taxes_current, property_taxes_year1,
  insurance_current, insurance_year1, repairs_maintenance_current, etc.). Map these
  directly to the schema's corresponding _current and _year1 fields.
- Phase 1 also emitted structure metadata fields. Use them to fill the six detected_*
  schema fields:
    operating_statement_column_structure -> parse into detected_current_column_label
      (the part before the first "|") and detected_year1_column_label (the "Year 1" part).
      Set detected_has_current_column=true when a current column is present, false
      when only Year-1 exists.
    expense_format -> detected_expense_format ("absolute", "per_sqft", or "mixed").
    income_period_label -> detected_income_period_label.
- When a _current value is 0, map it as 0.0 — do not omit it.
- When no _current variants appear in the condensed fields, set
  detected_has_current_column=false and leave all _current fields null.
- For gpr_annual_projected, vacancy_pct_projected, noi_projected: prefer Year-1
  condensed values over Current. Never use Pro Forma values for base-case inputs.
- When other income sub-categories are present (Administrative Fees, Late/Lien/NSF Fees, Tenant Insurance Net Commissions, Miscellaneous Income), populate BOTH other_income_annual (the aggregate sum) AND each individual other_income_*_annual field. Cite all contributing source tokens in other_income_annual.
- Map ALL operating expenses to one of the named expense fields when possible. If no named field matches, treat it as part of other_opex_annual. Never leave an expense line item unaccounted for.
- Never map the expense ratio percentage into any dollar field.
- For unit_mix rows, set climate_type to "CC" if the row is described as climate-controlled, temperature-controlled, heated, or humidity-controlled. Set it to "NC" if described as non-climate, drive-up, outdoor, or similar. Set it to "UNKNOWN" if unclear.
- Set unit_category to "storage" for standard storage units, "parking" for parking spaces, "residential" for apartments or dwelling units, "office" for office space, and "other" for anything else.
- avg_in_place_rent_per_unit_monthly: only when the OM explicitly states it as a single per-door aggregate figure. Do NOT derive or compute from unit-mix rows.
- mgmt_fee_pct: only when an explicit management fee percentage is stated in OM text; do not compute from the annual dollar amount.
- property_tax_growth_pct: only when a property-tax-specific growth rate is stated separately from opex_growth_pct; do not copy opex_growth_pct into this field."""

_T12_PHASE2_RULES = """T-12 / T-6 MAPPING RULES:
- Return source-period totals, not pre-annualized T-6 values. If the source covers 6 months, return the 6-month totals and set period_months = 6; the merger annualizes later.
- "Gross Potential Rent", "Scheduled Rent", "Gross Rental Income", "Rental Income" -> gpr_annual_actual
- "Vacancy", "Physical Vacancy", "Credit Loss", "Concessions", "Bad Debt" percentage -> vacancy_credit_loss_pct_actual as a decimal
- If vacancy, credit loss, concessions, or bad debt are shown as dollar lines and GPR is visible, compute vacancy_credit_loss_pct_actual from visible values only
- "Other Income", "Ancillary Income", "Admin Fees", "Late Fees", "Tenant Insurance", "Truck Rental", "Merchandise", "Locks", "Misc Income" -> other_income_annual
- "Bad Debt", "Write-offs", "Uncollectible" as a separate amount -> bad_debt_annual
- "Collections", "Corrections", "Prior Period Adjustments" -> corrections_collections_annual
- "Property Taxes", "Real Estate Taxes", "Tax Expense" -> property_tax_annual
- "Insurance", "Property Insurance", "Casualty", "Hazard" -> insurance_annual
- "Management Fee %" or stated management fee rate only -> mgmt_fee_pct_actual as a decimal. Dollar-only management fee lines -> other_opex_annual
- "Payroll", "Labor", "Salaries", "Benefits", "On-Site Manager" -> payroll_annual
- "Repairs", "Maintenance", "R&M", "Janitorial", "Cleaning", "Landscaping", "Pest Control" -> repairs_maintenance_annual
- "Utilities", "Electric", "Gas", "Water", "Trash", "Sewer" -> utilities_annual
- "Marketing", "Advertising", "Promotion", "Online Marketing", "Web Leads" -> marketing_annual
- All other operating expenses, including bank fees, merchant fees, software, telephone, security, gate/fire, office/admin, legal/professional, owner auto, travel, meals, and miscellaneous -> other_opex_annual
- "NOI", "Net Operating Income", "Net Income from Operations" -> noi_actual. If no NOI line is stated, compute only when total revenue and total operating expenses are visible.
- "Expense Ratio", "Opex Ratio" -> expense_ratio_actual as a decimal. If not stated, compute only when total operating expenses and effective gross income are visible.
- For monthly-column tables, prefer populated Total columns; otherwise sum visible month columns mechanically.
- For row-per-month tables, sum visible monthly rows for each mapped category.
- Set period_months from the visible month count: 12 for T-12, 6 for T-6, YTD count for YTD. Return null if unclear."""

_RENT_ROLL_PHASE2_RULES = """RENT ROLL MAPPING RULES:
- "Total Units", "Unit Count", occupied + vacant unit count -> num_units_actual
- "Occupancy", "Occupied %" -> physical_occupancy_pct as a decimal. If not stated, compute from visible occupied and total unit counts.
- "Average Rent", "Avg In-Place Rent", "Avg Monthly Rent Per Unit", current occupied rent aggregate -> avg_in_place_rent_per_unit_monthly
- Do not average market or street rents into avg_in_place_rent_per_unit_monthly.
- "Market Rent", "Street Rate", "Asking Rate", "Avg Market Rate" -> avg_market_rent_per_unit_monthly only when market-rate data exists.
- "Rent Growth", "Annual Rent Increase" -> rent_growth_pct as a decimal only when explicitly stated.
- Unit mix: preserve one row per size/type bucket. Use climate_type "CC" for climate/interior/temperature-controlled/heated/humidity-controlled; "NC" for non-climate/drive-up/outdoor/unconditioned; "UNKNOWN" when unclear.
- Unit category: "storage" for standard storage, "parking" for vehicle/RV/boat/parking rows, "residential" for apartments/dwellings, "office" for offices, "other" otherwise.
- Size must contain exactly one size bucket, e.g. "5 x 10". Do not collapse multiple sizes into one row.
- Lease records: one row per unit when row-level data exists. Use the schema field lease_expiration for the end date. monthly_rent = 0.0 for vacant units. sqft = unit square footage."""


def _phase2_system(
    doc_label: str,
    fields: list[dict],
    condensed_json: str,
    doc_rules: str = "",
) -> str:
    rules_section = f"\n{doc_rules}\n" if doc_rules else ""
    return f"""You are converting condensed field extractions into a typed {doc_label} underwriting schema.

The condensed data below was extracted from a real estate document.
Map field values to the schema. Rules:
- Monetary values: float, no symbols or commas
- Percentages: decimal (0.065 not 6.5%)
- If a value genuinely cannot be found, omit the field
{rules_section}

CITATIONS: For every SCALAR field you populate (not arrays like unit_mix, rent_comps, or lease_records), also emit the companion citation fields:
- {{field}}_confidence: your confidence 0.0-1.0
- {{field}}_citations: the S{{n}} source tokens from condensed_fields that contained this data (e.g. ["S1:p5"] or ["S1:Rent Roll!R2-R201"])
- {{field}}_source: verbatim snippet ≤40 chars — the key phrase only, no full sentences

Condensed data:
{condensed_json}

Before returning JSON, verify:
1. Every value you emit appears in the condensed data above — no invention
2. Numbers are floats, not strings and not raw percentages
3. Every populated scalar field has non-empty {{field}}_citations
4. Any field you are less than 60% confident about is omitted, not a guess

Return ONLY valid JSON matching this schema. Omit missing fields:
{_schema_json(fields)}"""


def create_phase2_om_prompt(condensed_json: str) -> str:
    return _phase2_system("Offering Memorandum (OM)", _OM_FIELDS, condensed_json, _OM_PHASE2_RULES)


def create_phase2_t12_prompt(condensed_json: str) -> str:
    return _phase2_system("T-12/T-6 Operating Statement", _T12_FIELDS, condensed_json, _T12_PHASE2_RULES)


def create_phase2_rent_roll_prompt(condensed_json: str) -> str:
    return _phase2_system("Rent Roll", _RENT_ROLL_FIELDS, condensed_json, _RENT_ROLL_PHASE2_RULES)
