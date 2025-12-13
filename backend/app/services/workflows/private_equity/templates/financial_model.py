"""Financial Model Builder workflow template definition.

Version: 1
Purpose: Generate forward-looking financial projections with scenario analysis for PE investment decisions.

JSON Contract (summary):
{
    historical: {
        revenue: [ { year, value, growth_rate?, citation } ],
        ebitda: [ { year, value, margin?, citation } ],
        key_metrics: { metric_name: { value, citation } }
    },
    assumptions: {
        base_case: { revenue_cagr, ebitda_margin_target, capex_percent_revenue, nwc_percent_revenue, citation[] },
        upside_case: { ... },
        downside_case: { ... }
    },
    projections: {
        base_case: [ { year, revenue, ebitda, ebitda_margin, fcf, citation[] } ],
        upside_case: [ ... ],
        downside_case: [ ... ]
    },
    valuation: {
        base_case: { exit_multiple, exit_ev, irr, moic, investment_amount?, citation[] },
        upside_case: { ... },
        downside_case: { ... }
    },
    sensitivity_analysis: [
        { variable, impact_on_irr, impact_on_moic, range_tested }
    ],
    key_drivers: [ { driver, description, impact, citation[] } ],
    risks_to_model: [ { risk, probability, impact_on_projections, mitigation } ],
    meta: { version: 1, projection_years, base_year }
}

Edge Cases:
- Missing historical data: Use available years, flag gaps in key_drivers
- Insufficient data for projections: Return conservative base case only
- Invalid assumptions (e.g., negative margins): Flag in risks_to_model
- Missing investment amount: Omit MOIC calculation, return IRR only
- Projection period < 3 years: Flag as warning in risks_to_model
"""

FINANCIAL_MODEL_PROMPT = """
Generate a comprehensive financial model for {{company_name}} with {{projection_years}}-year forward projections.

Objective:
Build a three-scenario financial model (Base, Upside, Downside) suitable for PE investment committee review. Include:
1. Historical financial analysis (revenue, EBITDA, margins, growth rates)
2. Explicit assumptions for each scenario with citations
3. Forward projections (P&L, cash flow metrics)
4. Valuation & returns analysis (IRR, MOIC, exit multiples)
5. Sensitivity analysis on key variables
6. Risk assessment for model assumptions

Dynamic Configuration (driven by variables):
- Include working capital projections if {{include_working_capital}} is true
- Include capex projections if {{include_capex}} is true
- Include debt service if {{include_debt}} is true
- Use {{projection_years}} for forecast period (default: 5 years)
- Target {{target_irr}} for return threshold context (default: 20%)

Instructions:

SECTION 1: HISTORICAL ANALYSIS
Extract and cite historical financials for the last {{historical_years}} years:
- Revenue (absolute values + YoY growth rates)
- EBITDA (absolute values + margins)
- Key operating metrics (if available: CAC, LTV, churn, unit economics)

Format:
"historical": {
    "revenue": [ { "year": 2022, "value": "$50M", "growth_rate": "15%", "citation": "[D1:p5]" } ],
    "ebitda": [ { "year": 2022, "value": "$10M", "margin": "20%", "citation": "[D1:p5]" } ],
    "key_metrics": { "CAC": { "value": "$500", "citation": "[D2:p12]" } }
}

SECTION 2: ASSUMPTIONS (THREE SCENARIOS)
Define assumptions for Base/Upside/Downside cases. Each assumption MUST cite supporting evidence.

Base Case:
- Revenue CAGR: Conservative growth based on historical trends + market growth
- EBITDA margin target: Achievable based on current margin + modest improvement
- Capex as % revenue: Historical average or industry benchmark
- Working capital as % revenue: Historical average

Upside Case:
- Revenue CAGR: Aggressive but realistic (cite market expansion, new products, etc.)
- EBITDA margin: Best-in-class for sector (cite comparable companies)
- Assume operational leverage, economies of scale

Downside Case:
- Revenue CAGR: Pessimistic (cite market headwinds, competitive threats)
- EBITDA margin compression (cite cost pressures, pricing pressure)

Format:
"assumptions": {
    "base_case": {
        "revenue_cagr": "12%",
        "ebitda_margin_target": "22%",
        "capex_percent_revenue": "5%",
        "nwc_percent_revenue": "10%",
        "citation": ["[D1:p8]", "[D3:p20]"]
    }
}

SECTION 3: PROJECTIONS
Generate year-by-year projections for {{projection_years}} years. Cite assumptions used.

Format (per scenario):
"projections": {
    "base_case": [
        {
            "year": 2025,
            "revenue": "$62M",
            "ebitda": "$13.6M",
            "ebitda_margin": "22%",
            "fcf": "$11M",
            "citation": ["[D1:p15]"]
        }
    ]
}

SECTION 4: VALUATION & RETURNS
Calculate exit valuation and investor returns for each scenario.

Required inputs (extract or infer):
- Exit multiple (EV/EBITDA) - cite comparable transactions or sector benchmarks
- Investment amount (equity check size) - if available
- Target exit year = base year + {{projection_years}}

Calculate:
- Exit EV = Final Year EBITDA × Exit Multiple
- IRR (Internal Rate of Return)
- MOIC (Multiple on Invested Capital) = Exit Value / Investment Amount

Format:
"valuation": {
    "base_case": {
        "exit_multiple": "10x",
        "exit_ev": "$150M",
        "irr": "22%",
        "moic": "3.0x",
        "investment_amount": "$50M",
        "citation": ["[D2:p30]", "[D4:p5]"]
    }
}

SECTION 5: SENSITIVITY ANALYSIS
Test impact of key variables on IRR/MOIC. Recommended variables:
- Revenue CAGR (±2%)
- Exit multiple (±1x)
- EBITDA margin (±2%)

Format:
"sensitivity_analysis": [
    {
        "variable": "Revenue CAGR",
        "impact_on_irr": "+2% CAGR → +3% IRR",
        "impact_on_moic": "+2% CAGR → +0.5x MOIC",
        "range_tested": "10%-14%"
    }
]

SECTION 6: KEY DRIVERS & RISKS
Identify key value drivers and risks to model assumptions.

Format:
"key_drivers": [
    { "driver": "Market expansion", "description": "TAM growing at 20% CAGR", "impact": "High", "citation": ["[D3:p12]"] }
],
"risks_to_model": [
    { "risk": "Customer concentration", "probability": "Medium", "impact_on_projections": "Could reduce revenue CAGR by 3-5%", "mitigation": "Diversification strategy" }
]

SECTION 7: METADATA
"meta": { "version": 1, "projection_years": {{projection_years}}, "base_year": <most recent historical year> }

CRITICAL RULES:
1. ALL quantitative claims must cite sources using [D#:p#] format
2. Use conservative assumptions for base case; cite reasoning
3. Ensure scenarios are internally consistent (upside > base > downside)
4. If data is missing, explicitly flag in risks_to_model rather than inventing numbers
5. Return STRICT JSON only, no commentary outside JSON structure

Return JSON with structure:
{
    "historical": {...},
    "assumptions": {...},
    "projections": {...},
    "valuation": {...},
    "sensitivity_analysis": [...],
    "key_drivers": [...],
    "risks_to_model": [...],
    "meta": {...}
}
""".strip()

FINANCIAL_MODEL_SCHEMA = {
    "variables": [
        {"name": "company_name", "type": "string", "required": True},
        {"name": "projection_years", "type": "integer", "default": 5, "min": 3, "max": 10},
        {"name": "historical_years", "type": "integer", "default": 3, "min": 2, "max": 5},
        {"name": "target_irr", "type": "integer", "default": 20, "min": 10, "max": 50},
        {"name": "include_working_capital", "type": "boolean", "default": True},
        {"name": "include_capex", "type": "boolean", "default": True},
        {"name": "include_debt", "type": "boolean", "default": False},
        {"name": "scenario_mode", "type": "enum", "choices": ["base_only", "three_scenario"], "default": "three_scenario"},
        {"name": "exit_multiple_assumption", "type": "number", "default": 10.0, "min": 5.0, "max": 20.0},
    ]
}

TEMPLATE = {
    "name": "Financial Model Builder",
    "domain": "private_equity",
    "category": "deal_flow",
    "description": "Forward-looking financial projections with scenario analysis and valuation",
    "prompt_template": FINANCIAL_MODEL_PROMPT,
    "variables_schema": FINANCIAL_MODEL_SCHEMA,
    "output_format": "json",
    "min_documents": 1,
    "max_documents": 5,
    "version": 1,
}
