# How to Fill in the Schema YAML

## Quick Start

1. Open your Excel template
2. Identify 50-100 most important cells
3. For each cell, add an entry to the YAML

## YAML Entry Template

```yaml
- id: "unique_field_id"           # Snake_case ID for this field
  sheet: "DASHBOARD"              # Exact sheet name
  label_cell: "B5"                # Cell containing the label
  value_cell: "C5"                # Cell where value should be filled
  data_type: "text"               # text, number, currency, percentage, date
  source_period: "static"         # current, t12, year1, pro_forma, stabilized, static
  source_basis: "om_property_summary"
  fill_when: ["always"]
  requires_structure: []          # e.g. ["column_map.year1"] for period-specific fields
  pdf_aliases:                    # What to look for in PDF (add many!)
    - "Primary Alias"
    - "Alternative Name"
    - "Common Abbreviation"
```

## Source Map Contract

The schema should describe when a field is allowed to be filled. The fill pipeline first detects an OM Source Map with operating-statement columns and section-presence flags. Fields that depend on a missing or low-confidence structure key are skipped with a structured reason instead of guessed.

Allowed `source_period` values:
- `current`
- `t12`
- `year1`
- `pro_forma`
- `stabilized`
- `static`

Allowed `source_basis` values:
- `om_operating_statement`
- `om_unit_mix`
- `om_property_summary`
- `om_market_summary`
- `om_rent_roll`
- `om_rent_comps`
- `om_capex_schedule`

Allowed `fill_when` values:
- `always`
- `current_operating_statement_present`
- `year1_operating_statement_present`
- `pro_forma_operating_statement_present`
- `t12_present`
- `unit_mix_present`
- `rent_roll_present`
- `rent_comps_present`
- `market_summary_present`

Structured skip reasons surfaced to review:
- `missing_section`
- `low_structure_confidence`
- `structure_key_missing`
- `data_type_mismatch`
- `extraction_returned_null`

Examples:

```yaml
- id: "actuals_real_estate_taxes"
  sheet: "Actuals&UnitMix"
  label_cell: "B19"
  value_cell: "C19"
  data_type: "currency"
  source_period: "current"
  source_basis: "om_operating_statement"
  fill_when: ["current_operating_statement_present"]
  requires_structure: ["column_map.current"]
  extraction_rule: "Use actual/current real estate taxes only. Do not use Year 1 or pro forma values."

- id: "pnl_year1_personnel_expense"
  sheet: "P&L"
  label_cell: "B32"
  value_cell: "E32"
  data_type: "currency"
  source_period: "year1"
  source_basis: "om_operating_statement"
  fill_when: ["year1_operating_statement_present"]
  requires_structure: ["column_map.year1"]
  extraction_rule: "Use Year 1 personnel/payroll expense. Do not use current or T12 actuals."
```

## Finding PDF Aliases

### Step 1: Upload a sample PDF
Run a fill with generic mapping and check the logs:
```
Detected PDF fields:
- "Purchase Price" = "$2,500,000"
- "Unit Count" = "48"
- "Yr Built" = "2015"
```

### Step 2: Add those names as aliases
```yaml
- id: "purchase_price"
  sheet: "DASHBOARD"
  value_cell: "C4"
  pdf_aliases:
    - "Purchase Price"    # ← From logs
    - "Asking Price"      # ← Common variation
    - "Sale Price"        # ← Another variation
```

### Step 3: Add variations proactively
Think about what different PDFs might call this field:
- **Purchase Price** could also be: "Listing Price", "Offer Price", "Price", "Sale Price"
- **Unit Count** could also be: "Units", "Total Units", "# Units", "Number of Units"
- **Year Built** could also be: "Built", "Construction Year", "Yr Built"

**Rule of thumb**: Add 3-5 aliases per field (common variations + abbreviations).

## Data Types

| data_type | Excel Format | Example Value |
|-----------|-------------|---------------|
| `text` | General | "123 Main St" |
| `number` | Number | 48 |
| `currency` | Currency ($) | $2,500,000 |
| `percentage` | Percentage (%) | 35% |
| `date` | Date | 12/31/2023 |

## Example: Property Info Section

```yaml
fields:
  # Property Name
  - id: "property_name"
    sheet: "DASHBOARD"
    label_cell: "B4"
    value_cell: "C4"
    data_type: "text"
    pdf_aliases:
      - "Property Name"
      - "Property"
      - "Building Name"
      - "Asset Name"

  # Property Address
  - id: "property_address"
    sheet: "DASHBOARD"
    label_cell: "B5"
    value_cell: "C5"
    data_type: "text"
    pdf_aliases:
      - "Property Address"
      - "Address"
      - "Location"
      - "Street Address"

  # Unit Count
  - id: "unit_count"
    sheet: "DASHBOARD"
    label_cell: "B6"
    value_cell: "C6"
    data_type: "number"
    pdf_aliases:
      - "Units"
      - "Unit Count"
      - "Total Units"
      - "# Units"
      - "Number of Units"
```

## Example: Financial Metrics

```yaml
fields:
  # Purchase Price
  - id: "purchase_price"
    sheet: "DASHBOARD"
    label_cell: "I4"
    value_cell: "J4"
    data_type: "currency"
    pdf_aliases:
      - "Purchase Price"
      - "Asking Price"
      - "Listing Price"
      - "Sale Price"
      - "Offer Price"
      - "Price"

  # Down Payment %
  - id: "down_payment_pct"
    sheet: "DASHBOARD"
    label_cell: "I5"
    value_cell: "J5"
    data_type: "percentage"
    pdf_aliases:
      - "Down Payment"
      - "Down Payment %"
      - "Equity %"
      - "Equity"
      - "DP%"
      - "Cash Investment"

  # Interest Rate
  - id: "interest_rate"
    sheet: "DASHBOARD"
    label_cell: "I6"
    value_cell: "J6"
    data_type: "percentage"
    pdf_aliases:
      - "Interest Rate"
      - "Rate"
      - "Loan Rate"
      - "Mortgage Rate"
      - "Note Rate"
      - "Int Rate"
```

## How to Find Label and Value Cells

### Method 1: Open Excel
1. Open your template in Excel
2. Find the field you want to map
3. Note the cells:
   - **Label cell**: Where the descriptive text is (e.g., "Unit Count" in B6)
   - **Value cell**: Where the value should go (e.g., empty cell C6)

### Method 2: Pattern Recognition
Most templates follow these patterns:

**Horizontal layout:**
```
B6: "Unit Count"  |  C6: [value goes here]
     ↑ label           ↑ value
```

**Vertical layout:**
```
C5: "Unit Count"
C6: [value goes here]
  ↑ label
  ↑ value (one row below)
```

## Tips for Finding Important Fields

### Priority 1: Property Basics (10 fields)
- Property name, address
- Unit count, square footage
- Year built
- Purchase price
- Property type

### Priority 2: Financial Metrics (15 fields)
- Purchase price, down payment
- Loan terms (rate, amortization, I/O period)
- NOI, cap rate
- Cash-on-cash return
- IRR

### Priority 3: Rent Roll Summary (10 fields)
- Total units
- Occupied units
- Vacancy rate
- Average rent
- Total rental income

### Priority 4: Operating Statement (15 fields)
- Gross potential rent
- Effective gross income
- Total expenses
- Net operating income
- Expense ratio

### Priority 5: Investment Structure (10 fields)
- LP/GP splits
- Preferred return
- Equity multiple
- Hold period
- Exit cap rate

**Total: 60 critical fields** - covers most important data points!

## Testing Your Schema

### Step 1: Save YAML
Save your changes to `re_investment_v1.yaml`.

### Step 2: Upload Template
Upload your Excel template to the system.

### Step 3: Check Identification
Look for this log line:
```
✓ Template identified as: re_investment_v1
```

If you see this, fingerprint matches! ✓

If not, check your fingerprint cells:
```yaml
fingerprint:
  - sheet: "DASHBOARD"
    cell: "B6"
    expected_value: "Unit Count"  # ← Must match EXACTLY
```

### Step 4: Run Fill
Upload a PDF and start a fill run.

Check logs for:
```
Schema mapping: 9 fields mapped (confidence=1.0)
```

The number should match how many fields you defined and PDF had data for.

### Step 5: Iterate
If fields aren't matching:
1. Check PDF field names in logs
2. Add missing aliases to YAML
3. Reload schema (restart worker or wait for auto-reload)
4. Try again

## Common Mistakes

### ❌ Wrong: Typo in sheet name
```yaml
sheet: "Dashboard"  # ← Case-sensitive!
```
Excel has: "DASHBOARD" (all caps)

### ❌ Wrong: Label cell instead of value cell
```yaml
value_cell: "B6"  # ← This is the LABEL cell!
```
Should be: `value_cell: "C6"` (empty cell where value goes)

### ❌ Wrong: Too few aliases
```yaml
pdf_aliases:
  - "Purchase Price"  # ← Only one alias
```
Add variations: "Asking Price", "Sale Price", "Price", etc.

### ✓ Correct Example
```yaml
- id: "purchase_price"
  sheet: "DASHBOARD"       # ← Exact sheet name (case-sensitive)
  label_cell: "I4"         # ← Cell with label text
  value_cell: "J4"         # ← Empty cell where value goes
  data_type: "currency"    # ← Matches Excel format
  pdf_aliases:             # ← Multiple variations
    - "Purchase Price"
    - "Asking Price"
    - "Listing Price"
    - "Sale Price"
    - "Price"
```

## Need Help?

1. Check logs for PDF field names
2. Compare to your aliases
3. Add missing variations
4. Test again

The system is forgiving - if schema doesn't match, LLM will still try!
