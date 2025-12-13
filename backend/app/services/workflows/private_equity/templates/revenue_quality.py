"""Revenue Quality Snapshot workflow template definition.
Version: 1
Purpose: Summarize revenue quality dimensions (growth, concentration, mix, seasonality, anomalies) for {{company_name}}.

JSON Contract (summary):
{
    growth: {
        cagr: str|number,
        year_breakdown: [ { year, revenue, citation } ]
    },
    concentration: [ { customer, percent, citation } ],
    recurring_mix: { recurring_percent, citation },
    seasonality: [ str ],
    anomalies: [ str ]
}

Edge Cases:
- Missing citation for a data point -> omit that item rather than include uncited.
- If year_breakdown has partial years, include only those with sourced revenue.
- Anomalies list may be empty; keep empty array.
- Percent values may be strings with % symbol or numeric; validator allows both.
"""

REVENUE_QUALITY_PROMPT = """
Create a revenue quality snapshot for {{company_name}} covering last {{years_back}} years.
Include: growth profile, concentration, recurring vs non-recurring mix, seasonality, anomaly notes.
Return JSON:\n{\n  "growth": { "cagr": str, "year_breakdown": [ { "year": int, "revenue": str, "citation": str } ] },\n  "concentration": [ { "customer": str, "percent": str, "citation": str } ],\n  "recurring_mix": { "recurring_percent": str, "citation": str },\n  "seasonality": [ str ],\n  "anomalies": [ str ]\n}\n""".strip()

REVENUE_QUALITY_SCHEMA = {
    "variables": [
        {"name": "company_name", "type": "string", "required": True},
        {"name": "years_back", "type": "integer", "default": 3, "min": 2, "max": 8},
    ]
}

TEMPLATE = {
    "name": "Revenue Quality Snapshot",
    "domain": "private_equity",
    "category": "diligence",
    "description": "Growth, concentration, mix and anomalies overview",
    "prompt_template": REVENUE_QUALITY_PROMPT,
    "variables_schema": REVENUE_QUALITY_SCHEMA,
    "output_format": "json",
    "min_documents": 1,
    "max_documents": 3,
    "version": 1,
}
